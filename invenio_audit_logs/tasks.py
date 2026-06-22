# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Celery tasks for audit log retention."""

from datetime import datetime, timezone

from celery import shared_task
from flask import current_app
from invenio_cache.lock import CachedMutex, LockAcquireFailed
from invenio_db import db
from invenio_search import current_search_client
from invenio_search.utils import build_alias_name
from sqlalchemy import and_, func, not_, or_

from .proxies import current_audit_logs_service
from .records.models import AuditLog, RetentionRun
from .retention import RetentionPolicy

LOCK_ID = "audit-logs-retention"
"""Cache key for the single-run lock guarding the retention task."""

LOCK_TIMEOUT = 60 * 60 * 23
"""Lock lifetime in seconds, below the monthly cadence so a stale lock clears."""


def _month_floor(dt):
    """Return the first instant of ``dt``'s month."""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(dt):
    """Return the first instant of the month after ``dt``."""
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1)
    return dt.replace(month=dt.month + 1)


def _naive_utc(dt):
    """Return ``dt`` as naive UTC to match the ``created`` column and cutoffs."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _expired_clause(finite_cutoffs):
    """Build a filter matching every expired event across all finite actions.

    An event is expired when its action has a finite period and its ``created``
    falls before that action's cutoff. The same clause drives both the OpenSearch
    deletion and, by negation, the survivor set, so the two stores agree on which rows
    a run removes.
    """
    return or_(
        *[
            and_(AuditLog.action == action, AuditLog.created < cutoff)
            for action, cutoff in finite_cutoffs.items()
        ]
    )


def _delete_from_opensearch(finite_cutoffs):
    """Drop or rebuild each month index, sourcing survivors from PostgreSQL.

    Expired events are deleted from OpenSearch before PostgreSQL, so survivors are read from the
    authoritative store while the expired rows it describes still exist. For every
    month that holds an expired event the stale ``auditlog-YYYY-MM`` index is
    deleted outright, so expired events vanish with their index rather than through
    ``delete_by_query``. A month that still holds survivors is then rebuilt from
    PostgreSQL: reindexing routes each survivor back into that same month by its
    ``created`` timestamp.
    """
    expired = _expired_clause(finite_cutoffs)
    service = current_audit_logs_service
    indexer = service.indexer
    record_cls = service.record_cls

    months = {
        _month_floor(_naive_utc(created))
        for (created,) in db.session.query(AuditLog.created).filter(expired).all()
    }

    rebuilt = False
    for month in months:
        survivors = [
            model_id
            for (model_id,) in db.session.query(AuditLog.id)
            .filter(
                AuditLog.created >= month,
                AuditLog.created < _next_month(month),
                not_(expired),
            )
            .all()
        ]
        index = build_alias_name(f"auditlog-{month:%Y-%m}")
        # Dropping the whole index removes the expired documents without
        # delete_by_query; the template recreates and re-aliases it on first write.
        current_search_client.indices.delete(index=index, ignore=[404])
        for model_id in survivors:
            indexer.index(record_cls.get_record(model_id))
            rebuilt = True
    if rebuilt:
        record_cls.index.refresh()


def _delete_range(action, start, end, batch_size):
    """Delete events of ``action`` with ``created`` in ``[start, end)``.

    Deletion keys on ``created`` rather than the id, so it is independent of the
    id version. Each batch commits on its own to keep locks and the write-ahead
    log small on the live table.
    """
    deleted = 0
    while True:
        ids = [
            row[0]
            for row in db.session.query(AuditLog.id)
            .filter(
                AuditLog.action == action,
                AuditLog.created >= start,
                AuditLog.created < end,
            )
            .limit(batch_size)
            .all()
        ]
        if not ids:
            break
        db.session.query(AuditLog).filter(AuditLog.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.session.commit()
        deleted += len(ids)
    return deleted


def _count_range(action, start, end):
    """Count events of ``action`` with ``created`` in ``[start, end)``.

    The dry-run counterpart to ``_delete_range``: it reads exactly the rows a real
    run would delete, so the preview matches what enforcement removes.
    """
    return (
        db.session.query(func.count(AuditLog.id))
        .filter(
            AuditLog.action == action,
            AuditLog.created >= start,
            AuditLog.created < end,
        )
        .scalar()
    )


def _expired_months(action, cutoff, batch_size, dry_run):
    """Walk the expired months of ``action`` and report rows per month.

    Walks whole calendar months from the oldest expired event up to ``cutoff``,
    which the resolver already snapped to a month boundary. A real run deletes each
    month's rows in bounded batches; a dry run only counts them and touches
    nothing. Returns a list of ``(month_start, rows)`` for the months with rows,
    so the caller records one retention run entry per deleted month and reports the
    same months in a dry run, matching how the partition-aware path will later
    operate on whole months.
    """
    oldest = (
        db.session.query(func.min(AuditLog.created))
        .filter(AuditLog.action == action, AuditLog.created < cutoff)
        .scalar()
    )
    if oldest is None:
        return []
    # The column reads back as UTC-aware; the cutoff and month walk are naive UTC.
    oldest = _naive_utc(oldest)

    per_month = []
    month = _month_floor(oldest)
    while month < cutoff:
        following = _next_month(month)
        if dry_run:
            rows = _count_range(action, month, following)
        else:
            rows = _delete_range(action, month, following, batch_size)
        if rows:
            per_month.append((month, rows))
        month = following
    return per_month


@shared_task(ignore_result=True)
def delete_expired_audit_logs(dry_run=False):
    """Delete expired audit log events from PostgreSQL.

    For every action present in the table the resolver decides whether the action
    is kept forever or yields a whole-month cutoff. Events older than the cutoff
    are deleted in bounded batches; kept-forever and not-yet-expired events stay.
    A single-run lock prevents overlapping runs, and the run is idempotent because
    a second pass finds nothing left past the cutoff.

    With ``dry_run`` the task counts what it would remove and reports it without
    deleting any row or writing a run log entry, so an operator can validate a
    policy change before enforcing it. The dry run reads the same months a real run
    would, so its counts match what the next enforced run deletes.

    Returns ``None`` when another run holds the lock. An enforced run returns a
    mapping of action id to the total rows it deleted. A dry run returns a mapping
    of action id to a per-month mapping of deleted month to the rows a real run
    would delete.

    Expired events are deleted from OpenSearch before PostgreSQL: a crash between the two leaves search
    showing fewer events than the authoritative store, never more, and a later run
    heals the drift from PostgreSQL.
    """
    lock = CachedMutex(LOCK_ID)
    try:
        lock.acquire(timeout=LOCK_TIMEOUT)
    except LockAcquireFailed:
        return None

    try:
        policy = RetentionPolicy.from_config(current_app.config)
        batch_size = current_app.config["AUDIT_LOGS_RETENTION_BATCH_SIZE"]
        # The ``created`` column is naive UTC, so compare against a naive cutoff.
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        actions = [row[0] for row in db.session.query(AuditLog.action).distinct().all()]
        finite_cutoffs = {
            action: policy.cutoff(action, now)
            for action in actions
            if not policy.is_kept_forever(action)
        }

        if not dry_run and finite_cutoffs:
            _delete_from_opensearch(finite_cutoffs)

        report = {}
        for action, cutoff in finite_cutoffs.items():
            per_month = _expired_months(action, cutoff, batch_size, dry_run)
            if not per_month:
                continue
            if dry_run:
                report[action] = {month.date(): rows for month, rows in per_month}
                continue
            retention_days = policy.period(action).days
            for month, deleted in per_month:
                db.session.add(
                    RetentionRun(
                        run_at=now,
                        action=action,
                        retention_days=retention_days,
                        month=month.date(),
                        rows_deleted=deleted,
                        status="success",
                    )
                )
            report[action] = sum(deleted for _, deleted in per_month)
        if not dry_run:
            db.session.commit()
        return report
    finally:
        lock.release()
