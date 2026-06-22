# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Celery tasks for audit log retention."""

from datetime import datetime, timezone

from celery import shared_task
from flask import current_app
from invenio_cache.lock import CachedMutex, LockAcquireFailed
from invenio_db import db
from sqlalchemy import func

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


def _delete_action(action, cutoff, batch_size):
    """Delete expired events of ``action`` month by month.

    Walks whole calendar months from the oldest expired event up to ``cutoff``,
    which the resolver already snapped to a month boundary. Returns a list of
    ``(month_start, rows_deleted)`` for the months that lost rows, so the caller
    can record one retention run entry per deleted month, matching how the
    partition-aware path will later operate on whole months.
    """
    oldest = (
        db.session.query(func.min(AuditLog.created))
        .filter(AuditLog.action == action, AuditLog.created < cutoff)
        .scalar()
    )
    if oldest is None:
        return []
    # The column reads back as UTC-aware; the cutoff and month walk are naive UTC.
    if oldest.tzinfo is not None:
        oldest = oldest.astimezone(timezone.utc).replace(tzinfo=None)

    per_month = []
    month = _month_floor(oldest)
    while month < cutoff:
        following = _next_month(month)
        deleted = _delete_range(action, month, following, batch_size)
        if deleted:
            per_month.append((month, deleted))
        month = following
    return per_month


@shared_task(ignore_result=True)
def delete_expired_audit_logs():
    """Delete expired audit log events from PostgreSQL.

    For every action present in the table the resolver decides whether the action
    is kept forever or yields a whole-month cutoff. Events older than the cutoff
    are deleted in bounded batches; kept-forever and not-yet-expired events stay.
    A single-run lock prevents overlapping runs, and the run is idempotent because
    a second pass finds nothing left past the cutoff.

    Returns a mapping of action id to the number of rows deleted, or ``None`` when
    another run holds the lock.
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

        deleted = {}
        for action in actions:
            if policy.is_kept_forever(action):
                continue
            cutoff = policy.cutoff(action, now)
            per_month = _delete_action(action, cutoff, batch_size)
            if not per_month:
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
            deleted[action] = sum(deleted for _, deleted in per_month)
        db.session.commit()
        return deleted
    finally:
        lock.release()
