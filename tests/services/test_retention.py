# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for audit log retention: resolver and the monthly DB delete."""

from datetime import datetime, timedelta, timezone

import pytest
from invenio_access.permissions import system_identity
from invenio_cache.lock import CachedMutex
from invenio_db import db

from invenio_audit_logs import KEEP_FOREVER
from invenio_audit_logs.records.models import AuditLog, RetentionRun
from invenio_audit_logs.retention import RetentionPolicy
from invenio_audit_logs.tasks import LOCK_ID, delete_expired_audit_logs

NOW = datetime(2026, 9, 15, 12, 30)
UTC = timezone.utc


@pytest.mark.parametrize(
    "action, periods, default, expected",
    [
        # Explicit per-action period: 60 days -> two whole months.
        (
            "user.login",
            {"user.login": timedelta(days=60)},
            timedelta(days=395),
            datetime(2026, 7, 1),
        ),
        # Default fallback: 395 days -> thirteen whole months.
        (
            "record.publish",
            {},
            timedelta(days=395),
            datetime(2025, 8, 1),
        ),
        # Kept forever: no cutoff.
        (
            "user.block",
            {"user.block": KEEP_FOREVER},
            timedelta(days=395),
            None,
        ),
    ],
)
def test_resolver_cutoff(action, periods, default, expected):
    """Resolver returns kept-forever or a whole-month cutoff per action."""
    policy = RetentionPolicy(periods, default)
    assert policy.cutoff(action, NOW) == expected


@pytest.mark.parametrize(
    "now, period, expected",
    [
        # Crossing a year boundary backwards.
        (datetime(2026, 1, 10), timedelta(days=60), datetime(2025, 11, 1)),
        # End-of-month reference still snaps to the first of the month.
        (datetime(2026, 3, 31, 23, 59), timedelta(days=90), datetime(2025, 12, 1)),
        # One month back from December.
        (datetime(2026, 12, 1), timedelta(days=30), datetime(2026, 11, 1)),
    ],
)
def test_resolver_month_boundary(now, period, expected):
    """The cutoff lands on a calendar-month boundary across year wraps."""
    policy = RetentionPolicy({"action": period}, timedelta(days=395))
    assert policy.cutoff("action", now) == expected


def test_resolver_keep_forever_flag():
    """is_kept_forever distinguishes the sentinel from a finite period."""
    policy = RetentionPolicy({"user.block": KEEP_FOREVER}, timedelta(days=395))
    assert policy.is_kept_forever("user.block") is True
    assert policy.is_kept_forever("user.login") is False


def _months_before(month_start, n):
    """Return the start of the month ``n`` months before ``month_start``."""
    total = month_start.year * 12 + (month_start.month - 1) - n
    year, month = divmod(total, 12)
    return month_start.replace(year=year, month=month + 1)


def _insert(action, created):
    """Insert an audit log row with a chosen ``created`` timestamp."""
    row = AuditLog(
        action=action,
        resource_type="record",
        user_id="1",
        json={},
        created=created,
        updated=created,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


@pytest.fixture()
def retention_config(set_app_config_fn_scoped):
    """Two-month logins, kept-forever blocks, 13-month default."""
    set_app_config_fn_scoped(
        {
            "AUDIT_LOGS_RETENTION": {
                "user.login": timedelta(days=60),
                "user.block": KEEP_FOREVER,
            },
            "AUDIT_LOGS_RETENTION_DEFAULT": timedelta(days=395),
        }
    )


@pytest.fixture()
def seeded_events(app, db, retention_config):
    """Seed events across months and actions with mixed retention."""
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        ids = {
            # Past the two-month login cutoff -> expired.
            "old_login": _insert("user.login", _months_before(month_start, 5)),
            # Current month -> within period, kept.
            "recent_login": _insert("user.login", now),
            # Kept forever regardless of age.
            "old_block": _insert("user.block", _months_before(month_start, 10)),
            # Within the 13-month default -> kept.
            "publish_recent": _insert("record.publish", _months_before(month_start, 5)),
            # Past the 13-month default -> expired.
            "publish_old": _insert("record.publish", _months_before(month_start, 20)),
        }
        yield ids


def _remaining_ids():
    """Return the set of ids currently in the table."""
    return {row[0] for row in db.session.query(AuditLog.id).all()}


def test_deletes_only_expired(app, seeded_events):
    """Only events past their action's cutoff are deleted; the rest remain."""
    with app.app_context():
        deleted = delete_expired_audit_logs()

        assert deleted == {"user.login": 1, "record.publish": 1}
        assert _remaining_ids() == {
            seeded_events["recent_login"],
            seeded_events["old_block"],
            seeded_events["publish_recent"],
        }


def test_delete_is_idempotent(app, seeded_events):
    """A second run deletes nothing and leaves the survivors untouched."""
    with app.app_context():
        delete_expired_audit_logs()
        survivors = _remaining_ids()

        deleted = delete_expired_audit_logs()

        assert deleted == {}
        assert _remaining_ids() == survivors


def test_delete_respects_single_run_lock(app, seeded_events):
    """A held lock blocks the run, so nothing is deleted."""
    with app.app_context():
        before = _remaining_ids()
        lock = CachedMutex(LOCK_ID)
        lock.acquire(timeout=60)
        try:
            deleted = delete_expired_audit_logs()
        finally:
            lock.release()

        assert deleted is None
        assert _remaining_ids() == before


def _runs():
    """Return the retention run log entries, ordered for stable assertions."""
    return (
        db.session.query(RetentionRun)
        .order_by(RetentionRun.action, RetentionRun.month)
        .all()
    )


def test_run_log_records_each_deleted_month(app, seeded_events):
    """One entry per deleted (action, month) carries its count, period, status."""
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        delete_expired_audit_logs()

        by_action = {run.action: run for run in _runs()}
        assert set(by_action) == {"user.login", "record.publish"}

        login = by_action["user.login"]
        assert login.month == _months_before(month_start, 5).date()
        assert login.rows_deleted == 1
        assert login.retention_days == 60
        assert login.status == "success"
        assert isinstance(login.run_at, datetime)

        publish = by_action["record.publish"]
        assert publish.month == _months_before(month_start, 20).date()
        assert publish.rows_deleted == 1
        assert publish.retention_days == 395
        assert publish.status == "success"


def test_run_log_one_entry_per_month_per_action(app, db, retention_config):
    """Expired rows of one action spread over months yield one entry each."""
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Two rows in the same expired month, one in an older expired month.
        _insert("user.login", _months_before(month_start, 4))
        _insert("user.login", _months_before(month_start, 4) + timedelta(days=1))
        _insert("user.login", _months_before(month_start, 6))

        delete_expired_audit_logs()

        logins = [run for run in _runs() if run.action == "user.login"]
        assert {(run.month, run.rows_deleted) for run in logins} == {
            (_months_before(month_start, 4).date(), 2),
            (_months_before(month_start, 6).date(), 1),
        }


def test_run_log_holds_no_event_content():
    """The run log table carries counts and status only, no event payload."""
    assert set(RetentionRun.__table__.columns.keys()) == {
        "id",
        "run_at",
        "action",
        "retention_days",
        "month",
        "rows_deleted",
        "status",
    }


def test_run_log_persists_across_runs(app, seeded_events):
    """Entries survive the deletion and a later no-op run, proving enforcement."""
    with app.app_context():
        delete_expired_audit_logs()
        first = {(run.action, run.month, run.rows_deleted) for run in _runs()}

        # A second run deletes nothing, yet the earlier proof stays in its own
        # table even though the audit rows it describes are gone.
        deleted = delete_expired_audit_logs()

        assert deleted == {}
        assert {(run.action, run.month, run.rows_deleted) for run in _runs()} == first
        assert len(first) == 2


def test_dry_run_reports_per_action_and_month(app, seeded_events):
    """A dry run reports the expired rows broken down by action and month."""
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        report = delete_expired_audit_logs(dry_run=True)

        assert report == {
            "user.login": {_months_before(month_start, 5).date(): 1},
            "record.publish": {_months_before(month_start, 20).date(): 1},
        }


def test_dry_run_deletes_nothing_in_postgres(app, seeded_events):
    """A dry run leaves every PostgreSQL row in place, expired or not."""
    with app.app_context():
        before = _remaining_ids()

        delete_expired_audit_logs(dry_run=True)

        assert _remaining_ids() == before
        # Reporting only; nothing claims a run happened.
        assert _runs() == []


def test_dry_run_counts_match_real_run(app, seeded_events):
    """The dry-run preview equals what the next enforced run actually deletes."""
    with app.app_context():
        report = delete_expired_audit_logs(dry_run=True)

        deleted = delete_expired_audit_logs()

        # Per-action totals reported by the dry run match the rows deleted.
        assert deleted == {
            action: sum(months.values()) for action, months in report.items()
        }
        # Per-month counts reported by the dry run match the run log entries.
        assert {(run.action, run.month, run.rows_deleted) for run in _runs()} == {
            (action, month, rows)
            for action, months in report.items()
            for month, rows in months.items()
        }


def test_dry_run_leaves_opensearch_searchable(app, service, resource_data):
    """A dry run touches no OpenSearch document, so expired events stay indexed."""
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        expired = _months_before(month_start, 20)

        # Create the event through the service so it lands in OpenSearch too, then
        # backdate the row in PostgreSQL. draft.create has no explicit period, so it
        # falls under the 13-month default and a 20-month-old event is expired. The
        # search index outlives a single test, so a unique resource id keeps this
        # event from colliding with other tests' draft.create events.
        resource_data["resource"]["id"] = "retention-dry-run"
        with app.test_request_context():
            service.create(identity=system_identity, data=resource_data)
        db.session.query(AuditLog).update(
            {AuditLog.created: expired, AuditLog.updated: expired}
        )
        db.session.commit()
        service.record_cls.index.refresh()

        report = delete_expired_audit_logs(dry_run=True)
        assert report == {"draft.create": {expired.date(): 1}}

        # The expired event is still in PostgreSQL and still searchable.
        assert len(_remaining_ids()) == 1
        found = service.search(
            identity=system_identity,
            params={"q": "resource.id: retention-dry-run AND action: draft.create"},
        )
        assert found.total == 1
