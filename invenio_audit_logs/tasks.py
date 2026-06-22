# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Celery tasks for audit log retention."""

from datetime import datetime, timezone

from celery import shared_task
from flask import current_app
from invenio_cache.lock import CachedMutex, LockAcquireFailed
from invenio_db import db

from .records.models import AuditLog
from .retention import RetentionPolicy

LOCK_ID = "audit-logs-retention"
"""Cache key for the single-run lock guarding the retention task."""

LOCK_TIMEOUT = 60 * 60 * 23
"""Lock lifetime in seconds, below the monthly cadence so a stale lock clears."""


def _delete_action(action, cutoff, batch_size):
    """Delete events of ``action`` created before ``cutoff`` in bounded batches.

    Deletion keys on ``created`` rather than the id, so it is independent of the
    id version. Each batch commits on its own to keep locks and the write-ahead
    log small on the live table.
    """
    deleted = 0
    while True:
        ids = [
            row[0]
            for row in db.session.query(AuditLog.id)
            .filter(AuditLog.action == action, AuditLog.created < cutoff)
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
            deleted = _delete_action(action, cutoff, batch_size)
            if deleted:
                deleted[action] = deleted
        return deleted
    finally:
        lock.release()
