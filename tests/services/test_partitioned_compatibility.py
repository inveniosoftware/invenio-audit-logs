# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Check the module works on a table partitioned by the UUIDv7 id.

A UUIDv7 starts with its creation time, so an operator can partition the table by
time using the id alone, with a tool like ``pg_partman`` and no extra column. These
tests create such a table and check that create, read, search, and the model still
work, because the module should not need to know the table is partitioned. The
retention side of this is in ``test_retention_partitioned.py``.
"""

import copy
from datetime import datetime, timedelta, timezone

import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_search import current_search_client
from sqlalchemy import text

from invenio_audit_logs.records.models import AuditLog


def _next_month(month_start):
    """Return the first day of the month after ``month_start``."""
    if month_start.month == 12:
        return month_start.replace(year=month_start.year + 1, month=1)
    return month_start.replace(month=month_start.month + 1)


def _uuid7_floor(month_start):
    """The smallest UUIDv7 for the start of a month, used as a partition boundary.

    It puts the month's millisecond timestamp at the front and zeros after it, so
    any real UUIDv7 from that month is equal to or greater than it.
    """
    ms = int(month_start.replace(tzinfo=timezone.utc).timestamp() * 1000)
    hexed = f"{ms:012x}"
    return f"{hexed[:8]}-{hexed[8:12]}-7000-8000-000000000000"


def _clear_audit_indices():
    """Delete the monthly ``auditlog`` indices so their documents don't reach other tests."""
    current_search_client.indices.delete(index="auditlog*", ignore_unavailable=True)


@pytest.fixture()
def partition_table(app, db, partition_audit_table):
    """Partition ``audit_logs_metadata`` by the UUIDv7 id, one child per month.

    ``partition_audit_table`` builds the table from the model; here we only list the
    monthly id ranges. These tests write through the service, so the search indices
    they fill are deleted at the end to keep their documents out of later tests.
    """
    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        curr_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month = (curr_month - timedelta(days=1)).replace(day=1)
        next_month = _next_month(curr_month)
        following_month = _next_month(next_month)

        children = {
            f"audit_logs_metadata_y{start.year}_m{start.month:02d}": (
                _uuid7_floor(start),
                _uuid7_floor(end),
            )
            for start, end in (
                (prev_month, curr_month),
                (curr_month, next_month),
                (next_month, following_month),
            )
        }
        partition_audit_table("RANGE (id)", children)

        _clear_audit_indices()
        yield
        _clear_audit_indices()


def test_basic_crud_with_partitioned_table(
    app, service, resource_data, client_with_login, partition_table
):
    """Create and read a log entry on the partitioned table."""
    with app.test_request_context():
        created = service.create(identity=system_identity, data=resource_data)
        fetched = service.read(identity=system_identity, id_=created.id)

    assert fetched["action"] == "draft.create"
    assert fetched["resource"]["id"] == "abcd-1234"
    assert fetched["user"]["id"] == "1"


def test_cross_partition_queries(
    app, service, resource_data, client_with_login, partition_table
):
    """Read several entries back and count them across the partitioned table."""
    with app.test_request_context():
        ids = []
        for n in range(1, 4):
            data = copy.deepcopy(resource_data)
            data["resource"]["id"] = f"resource-{n}"
            ids.append(service.create(identity=system_identity, data=data).id)

        for n, id_ in enumerate(ids, start=1):
            assert (
                service.read(identity=system_identity, id_=id_)["resource"]["id"]
                == f"resource-{n}"
            )

        count = db.session.execute(
            text("SELECT count(*) FROM audit_logs_metadata")
        ).scalar()
        assert count == 3


def test_search_with_partitioned_table(
    app, service, resource_data, client_with_login, partition_table
):
    """Index a log entry on the partitioned table and find it through search."""
    data = copy.deepcopy(resource_data)
    data["resource"]["id"] = "search-test-unique-id"

    with app.test_request_context():
        service.create(identity=system_identity, data=data)
        service.record_cls.index.refresh()

        results = service.search(
            identity=system_identity,
            params={"q": "resource.id: search-test-unique-id"},
        )

    assert results.total == 1
    hits = list(results.hits)
    assert hits[0]["resource"]["id"] == "search-test-unique-id"


def test_model_unaware_of_partitioning(app, partition_table):
    """The model still maps to one plain table with a single-column id key."""
    assert AuditLog.__tablename__ == "audit_logs_metadata"
    assert AuditLog.__table__.primary_key.columns.keys() == ["id"]

    table = db.metadata.tables["audit_logs_metadata"]
    assert {"id", "created", "action", "resource_type", "user_id"} <= set(
        table.columns.keys()
    )


def test_partition_count(app, partition_table):
    """The previous, current, and next month each get a child partition."""
    partitions = db.session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE tablename LIKE 'audit_logs_metadata_y%' ORDER BY tablename"
        )
    ).fetchall()
    names = [row[0] for row in partitions]

    assert len(names) == 3
    assert all(
        name.startswith("audit_logs_metadata_y") and "_m" in name for name in names
    )
