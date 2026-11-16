# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Celery tasks for audit log retention."""

import re
import time
import uuid
from datetime import datetime, timezone

from celery import shared_task
from flask import current_app
from invenio_cache.lock import CachedMutex, LockAcquireFailed
from invenio_db import db
from invenio_search import current_search_client
from invenio_search.utils import build_alias_name
from sqlalchemy import (
    and_,
    column,
    func,
    literal_column,
    not_,
    or_,
    select,
    table,
    text,
)

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


def _expired_clause(finite_cutoffs, source=AuditLog.__table__):
    """Match events whose ``created`` is before their action's cutoff.

    ``source`` lets the partition rewrite apply it to one child.
    """
    return or_(
        *[
            and_(source.c.action == action, source.c.created < cutoff)
            for action, cutoff in finite_cutoffs.items()
        ]
    )


def _expired_query(finite_cutoffs):
    """Match in OpenSearch the same events as ``_expired_clause``."""
    return {
        "bool": {
            "should": [
                {
                    "bool": {
                        "filter": [
                            {"term": {"action": action}},
                            {"range": {"@timestamp": {"lt": cutoff.isoformat()}}},
                        ]
                    }
                }
                for action, cutoff in finite_cutoffs.items()
            ],
            "minimum_should_match": 1,
        }
    }


def _reindex(source, dest, query):
    """Copy matching documents server-side, polled so no HTTP request stays open."""
    client = current_search_client
    task = client.reindex(
        body={"source": {"index": source, "query": query}, "dest": {"index": dest}},
        params={"wait_for_completion": "false", "refresh": "true"},
    )["task"]
    while not (result := client.tasks.get(task_id=task))["completed"]:
        time.sleep(5)
    if result.get("error") or result["response"]["failures"]:
        raise RuntimeError(f"reindex {source} -> {dest} failed: {result}")


def _delete_from_opensearch(finite_cutoffs, run_at):
    """Swap each month index holding expired events for a copy of its kept events.

    One atomic alias update moves the read aliases and the month name to the copy
    and deletes the old index, so search never sees a half-done month. Writes keep
    using ``auditlog-YYYY-MM``, which is the index or an alias of its latest copy.
    """
    client = current_search_client
    expired = _expired_query(finite_cutoffs)
    keep = {"bool": {"must_not": [expired]}}
    read_aliases = [build_alias_name("auditlog"), build_alias_name("audit-log")]
    if not client.indices.exists_alias(name=read_aliases[0]):
        return
    found = client.search(
        index=read_aliases[0],
        body={
            "size": 0,
            "query": expired,
            "aggs": {"index": {"terms": {"field": "_index", "size": 10000}}},
        },
    )
    for bucket in found["aggregations"]["index"]["buckets"]:
        current = bucket["key"]
        month = re.match(r".*auditlog-\d{4}-\d{2}", current).group()
        # Copies left by a run that died before its swap are not in any alias.
        for stale in client.indices.get_alias(index=f"{month}-*"):
            if stale != current:
                client.indices.delete(index=stale)
        kept = client.count(index=current, body={"query": keep})["count"]
        if not kept:
            client.indices.delete(index=current)
            continue
        copy = f"{month}-{run_at:%Y%m%d%H%M%S}"
        # The template joins every new auditlog* index to the read aliases; take
        # the copy out while it is empty so search never sees a half-filled copy.
        client.indices.create(index=copy)
        client.indices.update_aliases(
            body={
                "actions": [
                    {"remove": {"index": copy, "alias": alias}}
                    for alias in read_aliases
                ]
            }
        )
        _reindex(current, copy, keep)
        copied = client.count(index=copy)["count"]
        if copied != kept:
            raise RuntimeError(f"{copy} holds {copied} documents, expected {kept}")
        client.indices.update_aliases(
            body={
                "actions": [
                    *({"add": {"index": copy, "alias": a}} for a in read_aliases),
                    {"add": {"index": copy, "alias": month}},
                    {"remove_index": {"index": current}},
                ]
            }
        )


def _outside(skip):
    """Filter out rows stored in the ``skip`` child partitions (by table OID)."""
    if not skip:
        return True
    return literal_column("tableoid").notin_(skip)


class _RunLog:
    """Run log rows of one run, one per ``(action, month)``.

    Counts commit with each delete so they match what is gone; a row left
    ``running`` marks a worker that died mid-run.
    """

    def __init__(self, policy, run_at):
        """Start an empty log for a run at ``run_at``."""
        self.policy = policy
        self.run_at = run_at
        self.rows = {}

    def start(self, action, month):
        """Return the row for ``(action, month)``, committing it first if new."""
        key = (action, month)
        if key not in self.rows:
            row = RetentionRun(
                run_at=self.run_at,
                action=action,
                retention_months=self.policy.period(action),
                month=month.date(),
                rows_deleted=0,
                status="running",
            )
            db.session.add(row)
            db.session.commit()
            self.rows[key] = row
        return self.rows[key]

    def fail(self):
        """Mark every row this run did not finish as ``failed``."""
        db.session.rollback()
        for row in self.rows.values():
            if row.status == "running":
                row.status = "failed"
        db.session.commit()


def _delete_range(action, start, end, batch_size, log, skip=()):
    """Delete events of ``action`` in ``[start, end)`` in batches.

    Each batch commits with its run log count to keep locks and WAL small on the
    live table.
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
                _outside(skip),
            )
            .limit(batch_size)
            .all()
        ]
        if not ids:
            break
        run = log.start(action, start)
        db.session.query(AuditLog).filter(AuditLog.id.in_(ids)).delete(
            synchronize_session=False
        )
        run.rows_deleted += len(ids)
        db.session.commit()
        deleted += len(ids)
    if deleted:
        log.rows[(action, start)].status = "success"
        db.session.commit()
    return deleted


def _count_range(action, start, end, skip=()):
    """Count what ``_delete_range`` would delete, for dry runs."""
    return (
        db.session.query(func.count(AuditLog.id))
        .filter(
            AuditLog.action == action,
            AuditLog.created >= start,
            AuditLog.created < end,
            _outside(skip),
        )
        .scalar()
    )


def _expired_months(action, cutoff, batch_size, log, skip=()):
    """Delete (or with no ``log``, count) expired months of ``action``.

    Returns ``[(month, rows)]``. ``skip`` leaves out children the partition path
    already handled.
    """
    oldest = (
        db.session.query(func.min(AuditLog.created))
        .filter(AuditLog.action == action, AuditLog.created < cutoff, _outside(skip))
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
        if log is None:
            rows = _count_range(action, month, following, skip)
        else:
            rows = _delete_range(action, month, following, batch_size, log, skip)
        if rows:
            per_month.append((month, rows))
        month = following
    return per_month


def _is_partitioned():
    """Whether ``audit_logs_metadata`` is partitioned; the model stays unaware."""
    if db.engine.name != "postgresql":
        return False
    relkind = db.session.execute(
        text(
            "SELECT c.relkind FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :name AND n.nspname = 'public'"
        ),
        {"name": AuditLog.__tablename__},
    ).scalar()
    return relkind == "p"


def _cold_partitions(hot_start):
    """Return ``(oid, name)`` of children whose upper bound is before ``hot_start``.

    New rows never land there, so rewriting them does not block writes. Only
    ``RANGE (created)`` and ``RANGE (id)`` (UUIDv7) are understood; anything else
    goes through the batched path.
    """
    key = db.session.execute(
        text("SELECT pg_get_partkeydef(CAST(:t AS regclass))"),
        {"t": AuditLog.__tablename__},
    ).scalar()
    if key == "RANGE (created)":
        cast, limit = "timestamptz", hot_start.replace(tzinfo=timezone.utc)
    elif key == "RANGE (id)":
        ms = int(hot_start.replace(tzinfo=timezone.utc).timestamp() * 1000)
        cast, limit = "uuid", uuid.UUID(int=ms << 80)
    else:
        return []
    rows = db.session.execute(
        text(
            "SELECT oid, relname FROM ("
            " SELECT c.oid, c.relname, (regexp_match("
            "  pg_get_expr(c.relpartbound, c.oid), 'TO \\(''([^'']+)''\\)'))[1] AS upper"
            " FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid"
            " WHERE i.inhparent = CAST(:t AS regclass)) b "
            f"WHERE CAST(upper AS {cast}) <= :limit ORDER BY relname"
        ),
        {"t": AuditLog.__tablename__, "limit": limit},
    ).fetchall()
    return [(oid, name) for oid, name in rows]


def _purge_partition(name, finite_cutoffs, log):
    """Truncate one cold child, keeping its kept rows; return expired counts.

    Kept rows go through a temp table so only they reach the WAL, all in one
    transaction with the run log. Without a ``log`` (dry run) nothing changes.
    """
    child = table(name, column("id"), column("action"), column("created"))
    expired = _expired_clause(finite_cutoffs, child)
    month = func.date_trunc("month", func.timezone("UTC", child.c.created))
    counts = [
        (action, _naive_utc(m), rows)
        for action, m, rows in db.session.execute(
            select(child.c.action, month, func.count())
            .where(expired)
            .group_by(child.c.action, month)
        )
    ]
    if not counts or log is None:
        return counts

    runs = [(log.start(action, m), rows) for action, m, rows in counts]
    # Catalog names are not SQL-safe as-is (case, spaces), so quote before splicing.
    quoted = db.engine.dialect.identifier_preparer.quote(name)
    has_kept = db.session.execute(
        select(select(child.c.id).where(not_(expired)).exists())
    ).scalar()
    if has_kept:
        db.session.execute(text("DROP TABLE IF EXISTS _audit_kept"))
        kept_rows = (
            select(literal_column("*"))
            .select_from(child)
            .where(not_(expired))
            .compile(db.engine)
        )
        db.session.connection().exec_driver_sql(
            f"CREATE TEMP TABLE _audit_kept AS {kept_rows}", kept_rows.params
        )
        db.session.execute(text(f"TRUNCATE TABLE {quoted}"))
        db.session.execute(text(f"INSERT INTO {quoted} SELECT * FROM _audit_kept"))
        db.session.execute(text("DROP TABLE _audit_kept"))
    else:
        db.session.execute(text(f"TRUNCATE TABLE {quoted}"))
    for run, rows in runs:
        run.rows_deleted += rows
        run.status = "success"
    db.session.commit()
    return counts


def _delete_partitions(finite_cutoffs, now, batch_size, log):
    """Rewrite cold children whole, then batch-delete what is left elsewhere.

    Returns ``[(action, month, rows)]``.
    """
    cold = _cold_partitions(_month_floor(now))
    found = []
    for _, name in cold:
        found += _purge_partition(name, finite_cutoffs, log)
    skip = [oid for oid, _ in cold]
    for action, cutoff in finite_cutoffs.items():
        for month, rows in _expired_months(action, cutoff, batch_size, log, skip):
            found.append((action, month, rows))
    return found


@shared_task(ignore_result=True)
def delete_expired_audit_logs(dry_run=False):
    """Delete expired audit log events from OpenSearch, then PostgreSQL.

    OpenSearch goes first so search never lists an event PostgreSQL lacks; each
    store finds its own leftovers, so the next run finishes a crashed one.
    Returns ``None`` if locked, ``{action: {month: rows}}`` for a dry run (counts
    only, PostgreSQL only), else ``{action: rows_deleted}``.
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
        if not finite_cutoffs:
            return {}

        log = None if dry_run else _RunLog(policy, now)
        try:
            if log is not None:
                _delete_from_opensearch(finite_cutoffs, now)
            if _is_partitioned():
                found = _delete_partitions(finite_cutoffs, now, batch_size, log)
            else:
                found = [
                    (action, month, rows)
                    for action, cutoff in finite_cutoffs.items()
                    for month, rows in _expired_months(action, cutoff, batch_size, log)
                ]
        except Exception:
            if log is not None:
                log.fail()
            raise

        report = {}
        for action, month, rows in found:
            if dry_run:
                per_month = report.setdefault(action, {})
                per_month[month.date()] = per_month.get(month.date(), 0) + rows
            else:
                report[action] = report.get(action, 0) + rows
        return report
    finally:
        lock.release()
