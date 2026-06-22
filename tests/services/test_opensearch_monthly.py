# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the monthly OpenSearch storage of audit logs.

The search copy lives in plain ``auditlog-YYYY-MM`` indices behind the
``auditlog`` read alias instead of a managed data stream. These tests assert the
external behaviour: where new writes land, that search through the alias spans
every month, that existing PostgreSQL rows reindex into the monthly layout
without loss, and that no data stream, write alias, or rollover job is involved.
"""

from datetime import datetime, timezone

from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_search import current_search_client
from invenio_search.utils import build_alias_name

from invenio_audit_logs.records.models import AuditLog


def _month_index(dt):
    """Return the prefixed name of the monthly index for ``dt``."""
    return build_alias_name(f"auditlog-{dt:%Y-%m}")


def _months_before(dt, n):
    """Return ``dt`` shifted back by whole ``n`` months."""
    total = dt.year * 12 + (dt.month - 1) - n
    year, month = divmod(total, 12)
    return dt.replace(
        year=year, month=month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _insert(action, created, resource_id):
    """Insert an audit log row straight into PostgreSQL with a chosen month.

    Bypasses the service so the row exists only in PostgreSQL, mimicking history
    that predates the monthly indices and must be reindexed into them.
    """
    row = AuditLog(
        action=action,
        resource_type="record",
        user_id="1",
        json={
            "resource": {"type": "record", "id": resource_id},
            "user": {
                "id": "1",
                "username": "User",
                "email": "user@inveniosoftware.org",
            },
            "message": "event",
            "metadata": {},
        },
        created=created,
        updated=created,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _auditlog_templates():
    """Return the registered index templates that match ``auditlog*``."""
    templates = current_search_client.indices.get_index_template(name="*auditlog*")
    return [
        entry
        for entry in templates["index_templates"]
        if any("auditlog" in p for p in entry["index_template"]["index_patterns"])
    ]


def test_template_declares_no_data_stream(app):
    """The auditlog index templates are plain templates, not data streams."""
    with app.app_context():
        templates = _auditlog_templates()
        assert templates  # the template is registered at all
        for entry in templates:
            assert "data_stream" not in entry["index_template"]


def test_write_lands_in_monthly_index_under_read_alias(app, db, service, resource_data):
    """A new write creates ``auditlog-YYYY-MM`` and joins it to the read alias."""
    # The OpenSearch copy outlives a single test, so a unique resource id keeps
    # this event from colliding with other tests' draft.create events.
    resource_data["resource"]["id"] = "monthly-write"
    with app.test_request_context():
        service.create(identity=system_identity, data=resource_data)
    service.record_cls.index.refresh()

    now = datetime.now(timezone.utc)
    month_index = _month_index(now)
    alias = build_alias_name("auditlog")
    client = current_search_client

    # The month index was auto-created on first write.
    assert client.indices.exists(index=month_index)
    # ...and the read alias points at it with no write-index flag (no write alias).
    alias_entry = client.indices.get_alias(index=month_index)[month_index]["aliases"]
    assert alias in alias_entry
    assert alias_entry[alias].get("is_write_index") is not True

    # The event is searchable through the alias.
    found = service.search(
        identity=system_identity,
        params={"q": "resource.id: monthly-write AND action: draft.create"},
    )
    assert found.total == 1


def test_no_data_stream_or_rollover(app, db, service, resource_data):
    """Writing creates no data stream and needs no rollover job."""
    resource_data["resource"]["id"] = "monthly-no-stream"
    with app.test_request_context():
        service.create(identity=system_identity, data=resource_data)
    service.record_cls.index.refresh()

    client = current_search_client
    assert client.indices.get_data_stream(name="*auditlog*")["data_streams"] == []


def test_reindex_spreads_existing_data_across_months(app, db, service):
    """Reindexing routes each PostgreSQL row into its own month with no loss."""
    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        months = {
            "current": (this_month, "monthly-current"),
            "five_back": (_months_before(this_month, 5), "monthly-five-back"),
            "twenty_back": (_months_before(this_month, 20), "monthly-twenty-back"),
        }
        for created, rid in months.values():
            _insert("draft.create", created, rid)

        reindexed = service.reindex(identity=system_identity)
        assert reindexed == 3
        service.record_cls.index.refresh()

        client = current_search_client
        # Each row landed in the index for its own month, and nowhere else.
        for created, rid in months.values():
            index = _month_index(created)
            hits = client.search(
                index=index,
                body={"query": {"term": {"resource.id": rid}}},
            )
            assert hits["hits"]["total"]["value"] == 1

        # Search through the alias spans all three months with no duplicates.
        for created, rid in months.values():
            found = service.search(
                identity=system_identity,
                params={"q": f"resource.id: {rid} AND action: draft.create"},
            )
            assert found.total == 1

        all_hits = service.search(
            identity=system_identity,
            params={"q": "action: draft.create", "size": 100},
        )
        seen = {hit["resource"]["id"] for hit in all_hits.hits}
        assert {rid for _, rid in months.values()} <= seen
