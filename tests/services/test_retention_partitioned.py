# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Retention against a monthly-partitioned ``audit_logs_metadata``.

The default profile deletes scattered rows in batches; the scale profile lets an
operator partition the table by month and the task then drops or rewrites whole
cold partitions instead. Both profiles must reach the same end state, so these
tests seed an operator-style partitioned table and assert the same survivors the
batched path produces, plus that the rewrite touches only cold children.

The fixture partitions on ``created`` rather than the UUIDv7 id used by the
prior-art ``test_partitioned_compatibility.py``. Until the id migration lands the
model still issues uuid4 ids, which would fall outside any id-based partition
range; partitioning on ``created`` matches how retention keys its cutoffs and
keeps the task's partition handling agnostic to the partition key. The setup runs
inside the test's own transaction, so the savepoint-based ``db`` fixture rolls the
table back to a plain table after each test with no leakage.
"""

from datetime import datetime, timedelta, timezone

import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from sqlalchemy import text

from invenio_audit_logs import KEEP_FOREVER
from invenio_audit_logs.records.models import AuditLog, RetentionRun
from invenio_audit_logs.tasks import delete_expired_audit_logs

UTC = timezone.utc


def _months_before(month_start, n):
    """Return the start of the month ``n`` months before ``month_start``."""
    total = month_start.year * 12 + (month_start.month - 1) - n
    year, month = divmod(total, 12)
    return month_start.replace(year=year, month=month + 1)


def _next_month(month_start):
    """Return the first instant of the month after ``month_start``."""
    if month_start.month == 12:
        return month_start.replace(year=month_start.year + 1, month=1)
    return month_start.replace(month=month_start.month + 1)


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


def _remaining_ids():
    """Return the set of ids currently in the table."""
    return {row[0] for row in db.session.query(AuditLog.id).all()}


def _partition_names():
    """Return the monthly child partitions, ordered by name."""
    rows = db.session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE tablename LIKE 'audit_logs_metadata_y%' ORDER BY tablename"
        )
    ).fetchall()
    return [row[0] for row in rows]


@pytest.fixture()
def retention_config(set_app_config_fn_scoped):
    """Two-month logins, kept-forever blocks, 13-month default.

    ``draft.create`` is kept forever too: it is a registered action, so it can
    stand as a survivor that the OpenSearch rebuild reindexes from PostgreSQL,
    which an unregistered action could not.
    """
    set_app_config_fn_scoped(
        {
            "AUDIT_LOGS_RETENTION": {
                "user.login": timedelta(days=60),
                "user.block": KEEP_FOREVER,
                "draft.create": KEEP_FOREVER,
            },
            "AUDIT_LOGS_RETENTION_DEFAULT": timedelta(days=395),
        }
    )


@pytest.fixture()
def partitioned_table(app, db, retention_config):
    """Convert ``audit_logs_metadata`` to a monthly-partitioned table.

    Mirrors what an operator would set up with tooling such as ``pg_partman``:
    drop the plain table and recreate it ranged by ``created``, with one child per
    month from two years back through next month. The current and next months
    cover live ingestion; the older children are the cold partitions retention
    operates on. PostgreSQL requires the range key in the primary key, so the key
    becomes ``(id, created)``; the SQLAlchemy model keeps its single-column id key
    and never sees this.
    """
    if db.engine.name != "postgresql":
        pytest.skip("Partitioning only runs on PostgreSQL")

    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        db.session.execute(text("DROP TABLE audit_logs_metadata"))
        db.session.execute(
            text(
                """
                CREATE TABLE audit_logs_metadata (
                    id UUID NOT NULL,
                    created TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    updated TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    action VARCHAR(255) NOT NULL,
                    resource_type VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    json JSONB,
                    version_id INTEGER NOT NULL,
                    PRIMARY KEY (id, created)
                ) PARTITION BY RANGE (created)
                """
            )
        )
        for n in range(24, -2, -1):
            start = _months_before(month_start, n)
            end = _next_month(start)
            name = f"audit_logs_metadata_y{start.year}_m{start.month:02d}"
            db.session.execute(
                text(
                    f"CREATE TABLE {name} PARTITION OF audit_logs_metadata "
                    f"FOR VALUES FROM ('{start:%Y-%m-%d}') TO ('{end:%Y-%m-%d}')"
                )
            )
        db.session.commit()
        yield month_start


def test_fully_expired_partition_is_emptied(app, partitioned_table):
    """A cold month whose every row is expired is cleared down to nothing."""
    with app.app_context():
        month_start = partitioned_table
        # 20 months old, only default-retention actions: the whole month expires.
        expired_month = _months_before(month_start, 20)
        a = _insert("record.publish", expired_month)
        b = _insert("record.publish", expired_month + timedelta(days=3))

        partition = (
            f"audit_logs_metadata_y{expired_month.year}_m{expired_month.month:02d}"
        )
        before = db.session.execute(text(f"SELECT count(*) FROM {partition}")).scalar()
        assert before == 2

        deleted = delete_expired_audit_logs()

        assert deleted == {"record.publish": 2}
        assert _remaining_ids() == set()
        # The partition is truncated, not dropped: it survives for future writes.
        assert partition in _partition_names()
        after = db.session.execute(text(f"SELECT count(*) FROM {partition}")).scalar()
        assert after == 0
        assert {a, b}.isdisjoint(_remaining_ids())


def test_partition_with_survivors_is_rewritten(app, partitioned_table):
    """A cold month keeps its survivors and loses only its expired rows."""
    with app.app_context():
        month_start = partitioned_table
        # Five months back: the login (two-month period) expires, the kept-forever
        # creation survives, so the cold child must be rewritten down to it.
        cold_month = _months_before(month_start, 5)
        expired_login = _insert("user.login", cold_month)
        kept = _insert("draft.create", cold_month + timedelta(days=2))

        partition = f"audit_logs_metadata_y{cold_month.year}_m{cold_month.month:02d}"

        deleted = delete_expired_audit_logs()

        assert deleted == {"user.login": 1}
        # The survivor stays, with its original id, in the same partition.
        assert _remaining_ids() == {kept}
        assert expired_login not in _remaining_ids()
        held = db.session.execute(text(f"SELECT id::text FROM {partition}")).fetchall()
        assert [row[0] for row in held] == [str(kept)]


def test_current_partition_is_untouched(app, partitioned_table):
    """The hot current month is never read or rewritten by the task."""
    with app.app_context():
        month_start = partitioned_table
        now = datetime.now(UTC).replace(tzinfo=None)
        # A recent login (within its period) and an old login that must expire.
        recent = _insert("user.login", now)
        old = _insert("user.login", _months_before(month_start, 5))

        current_partition = (
            f"audit_logs_metadata_y{month_start.year}_m{month_start.month:02d}"
        )

        deleted = delete_expired_audit_logs()

        assert deleted == {"user.login": 1}
        assert _remaining_ids() == {recent}
        assert old not in _remaining_ids()
        # The current partition still holds exactly the recent row, untouched.
        held = db.session.execute(
            text(f"SELECT id::text FROM {current_partition}")
        ).fetchall()
        assert [row[0] for row in held] == [str(recent)]


def test_partitioned_matches_default_outcome(app, partitioned_table):
    """The partitioned profile leaves the same survivors as the batched path.

    The seed and expected survivors match ``test_deletes_only_expired`` in
    ``test_retention.py``, which runs the batched DELETE on a plain table. Equal
    survivors and an equal report show the two profiles share retention semantics.
    """
    with app.app_context():
        month_start = partitioned_table
        now = datetime.now(UTC).replace(tzinfo=None)
        ids = {
            "old_login": _insert("user.login", _months_before(month_start, 5)),
            "recent_login": _insert("user.login", now),
            "old_block": _insert("user.block", _months_before(month_start, 10)),
            "publish_recent": _insert("record.publish", _months_before(month_start, 5)),
            "publish_old": _insert("record.publish", _months_before(month_start, 20)),
        }

        deleted = delete_expired_audit_logs()

        assert deleted == {"user.login": 1, "record.publish": 1}
        assert _remaining_ids() == {
            ids["recent_login"],
            ids["old_block"],
            ids["publish_recent"],
        }


def test_partitioned_run_is_idempotent(app, partitioned_table):
    """A second partitioned run drops nothing and keeps the survivors."""
    with app.app_context():
        month_start = partitioned_table
        _insert("user.login", _months_before(month_start, 5))
        _insert("user.block", _months_before(month_start, 10))

        delete_expired_audit_logs()
        survivors = _remaining_ids()

        deleted = delete_expired_audit_logs()

        assert deleted == {}
        assert _remaining_ids() == survivors


def test_partitioned_run_log_records_each_month(app, partitioned_table):
    """One run-log entry per deleted month, matching the batched profile."""
    with app.app_context():
        month_start = partitioned_table
        _insert("user.login", _months_before(month_start, 4))
        _insert("user.login", _months_before(month_start, 4) + timedelta(days=1))
        _insert("user.login", _months_before(month_start, 6))

        delete_expired_audit_logs()

        logins = (
            db.session.query(RetentionRun)
            .filter(RetentionRun.action == "user.login")
            .all()
        )
        assert {(run.month, run.rows_deleted) for run in logins} == {
            (_months_before(month_start, 4).date(), 2),
            (_months_before(month_start, 6).date(), 1),
        }


def test_partitioned_dry_run_changes_nothing(app, partitioned_table):
    """A dry run reports the expired rows but writes nothing to either store."""
    with app.app_context():
        month_start = partitioned_table
        expired_month = _months_before(month_start, 20)
        _insert("record.publish", expired_month)
        before = _remaining_ids()

        report = delete_expired_audit_logs(dry_run=True)

        assert report == {"record.publish": {expired_month.date(): 1}}
        assert _remaining_ids() == before
        assert db.session.query(RetentionRun).count() == 0


def test_model_and_service_unaware_of_partitioning(
    app, service, resource_data, partitioned_table
):
    """The model stays single-table and the service reads and writes normally."""
    with app.app_context():
        # The model still maps to one plain table with a single-column id key.
        assert AuditLog.__tablename__ == "audit_logs_metadata"
        assert AuditLog.__table__.primary_key.columns.keys() == ["id"]

        resource_data["resource"]["id"] = "partitioned-transparency"
        with app.test_request_context():
            created = service.create(identity=system_identity, data=resource_data)
            fetched = service.read(identity=system_identity, id_=created.id)

        assert fetched["resource"]["id"] == "partitioned-transparency"
        assert fetched["action"] == "draft.create"
