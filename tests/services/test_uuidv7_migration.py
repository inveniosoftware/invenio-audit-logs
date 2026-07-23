# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the migration that changes existing ids to UUIDv7.

The migration rebuilds each id from the row's ``created`` time so the table can be
partitioned by time. These tests run the migration's own SQL on some seeded rows
and check that the ids become UUIDv7 in time order, that the count and uniqueness
hold, that retention still deletes by ``created`` (not by id), and that the search
copy can be rebuilt with the new ids.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_search import current_search_client
from sqlalchemy import text

import invenio_audit_logs
from invenio_audit_logs.records.models import AuditLog
from invenio_audit_logs.tasks import delete_expired_audit_logs

UTC = timezone.utc


def _migration_sql():
    """Read the rewrite SQL from the migration file so the test runs the real thing.

    The ``alembic`` folder is not a Python package, so the file is loaded by path
    instead of imported.
    """
    path = (
        Path(invenio_audit_logs.__file__).parent
        / "alembic"
        / "f0e1d2c3b4a5_rewrite_ids_to_uuid7.py"
    )
    spec = importlib.util.spec_from_file_location("_rewrite_ids_to_uuid7", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.REWRITE_IDS_TO_UUID7


REWRITE_SQL = _migration_sql()


def _ts_ms(value):
    """Get the millisecond timestamp back out of a UUIDv7."""
    return (value.int >> 80) & ((1 << 48) - 1)


def _insert(id_, action, created):
    """Insert an audit log row with a chosen id and ``created`` timestamp."""
    row = AuditLog(
        id=id_,
        action=action,
        resource_type="record",
        user_id="1",
        json={},
        created=created,
        updated=created,
    )
    db.session.add(row)
    db.session.commit()
    return id_


def _rewrite():
    """Run the migration's rewrite SQL and refresh the session's view of the rows."""
    db.session.execute(text(REWRITE_SQL))
    db.session.expire_all()


@pytest.fixture(autouse=True)
def _clean_audit_search(app):
    """Delete the monthly ``auditlog`` indices a test fills so they don't reach the next."""
    yield
    with app.app_context():
        current_search_client.indices.delete(index="auditlog*", ignore_unavailable=True)


def test_rewrite_replaces_uuid4_with_uuid7_derived_from_created(app, db):
    """Every id becomes a unique UUIDv7 based on its ``created`` time."""
    if db.engine.name != "postgresql":
        pytest.skip("Id rewrite runs against PostgreSQL")

    with app.app_context():
        seeds = {
            uuid4(): ("user.login", datetime(2024, 3, 10, 8, 30)),
            uuid4(): ("record.publish", datetime(2025, 7, 2, 9, 0)),
            uuid4(): ("user.login", datetime(2025, 7, 2, 9, 0)),
        }
        for old_id, (action, created) in seeds.items():
            _insert(old_id, action, created)

        _rewrite()

        rows = db.session.query(AuditLog).all()
        new_ids = {row.id for row in rows}

        assert len(new_ids) == 3
        assert new_ids.isdisjoint(seeds.keys())
        for row in rows:
            assert row.id.version == 7
            expected = int(row.created.replace(tzinfo=UTC).timestamp() * 1000)
            assert _ts_ms(row.id) == expected


def test_rewrite_preserves_time_order(app, db):
    """After the rewrite, an earlier ``created`` gives a smaller id than a later one."""
    if db.engine.name != "postgresql":
        pytest.skip("Id rewrite runs against PostgreSQL")

    with app.app_context():
        _insert(uuid4(), "user.login", datetime(2020, 1, 1))
        _insert(uuid4(), "user.login", datetime(2026, 1, 1))

        _rewrite()

        ordered = db.session.query(AuditLog).order_by(AuditLog.created).all()
        assert ordered[0].id < ordered[1].id


def test_retention_still_keys_on_created_after_rewrite(
    app, db, set_app_config_fn_scoped
):
    """Rewriting ids does not change which rows retention expires."""
    if db.engine.name != "postgresql":
        pytest.skip("Retention runs against PostgreSQL")

    set_app_config_fn_scoped(
        {
            "AUDIT_LOGS_RETENTION": {"user.login": timedelta(days=60)},
            "AUDIT_LOGS_RETENTION_DEFAULT": timedelta(days=395),
        }
    )

    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        _insert(uuid4(), "user.login", now)
        _insert(uuid4(), "user.login", now - timedelta(days=200))

        _rewrite()

        deleted = delete_expired_audit_logs()

        survivors = db.session.query(AuditLog).all()
        assert deleted == {"user.login": 1}
        assert len(survivors) == 1
        assert survivors[0].created.date() == now.date()


def test_reindex_after_rewrite_is_searchable(app, db, service):
    """The search copy can be rebuilt from PostgreSQL with the new ids."""
    if db.engine.name != "postgresql":
        pytest.skip("Reindex runs against PostgreSQL and OpenSearch")

    with app.app_context():
        _insert(uuid4(), "draft.create", datetime.now(UTC).replace(tzinfo=None))

        _rewrite()
        new_id = db.session.query(AuditLog.id).scalar()

        reindexed = service.reindex(system_identity)
        service.record_cls.index.refresh()
        with app.test_request_context():
            results = service.search(
                identity=system_identity, params={"q": "action: draft.create"}
            )

        assert new_id.version == 7
        assert reindexed == 1
        assert results.total == 1
