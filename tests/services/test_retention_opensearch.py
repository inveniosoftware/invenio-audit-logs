# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the OpenSearch side of audit log retention.

The retention task cleans search before PostgreSQL. A month with nothing to keep
has its ``auditlog-YYYY-MM`` index deleted; a month that still holds kept events is
copied into a new index and swapped in under the month name and read aliases.
"""

from datetime import datetime, timezone

import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_search import current_search, current_search_client
from invenio_search.utils import build_alias_name

from invenio_audit_logs import KEEP_FOREVER
from invenio_audit_logs.records.models import AuditLog, RetentionRun
from invenio_audit_logs.tasks import _delete_from_opensearch, delete_expired_audit_logs

UTC = timezone.utc


def _months_before(dt, n):
    """Return the start of the month ``n`` months before ``dt``."""
    total = dt.year * 12 + (dt.month - 1) - n
    year, month = divmod(total, 12)
    return dt.replace(
        year=year, month=month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _month_index(dt):
    """Return the prefixed name of the monthly index for ``dt``."""
    return build_alias_name(f"auditlog-{dt:%Y-%m}")


def _concrete(name):
    """Return the index behind ``name`` (an index or a single-index alias), or None."""
    info = current_search_client.indices.get(index=name, ignore=[404])
    if "error" in info:
        return None
    (index,) = info
    return index


def _make_event(service, action, created, resource_id):
    """Create an event in both PostgreSQL and its monthly OpenSearch index."""
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
    service.indexer.index(service.record_cls.get_record(row.id))
    return row.id


def _found(service, resource_id, action):
    """Return how many events match ``resource_id`` and ``action`` via the alias."""
    result = service.search(
        identity=system_identity,
        params={"q": f"resource.id: {resource_id} AND action: {action}"},
    )
    return result.total


def _pg_ids():
    """Return the set of audit log ids currently in PostgreSQL."""
    return {row[0] for row in db.session.query(AuditLog.id).all()}


@pytest.fixture(autouse=True)
def empty_month_indices(app):
    """Delete month indices left by earlier tests, which share the cluster."""
    current_search_client.indices.delete(
        index=build_alias_name("auditlog-*"), ignore_unavailable=True
    )


@pytest.fixture()
def keep_publish_forever(set_app_config_fn_scoped):
    """Keep ``record.publish`` forever; everything else uses the 13-month default."""
    set_app_config_fn_scoped({"AUDIT_LOGS_RETENTION": {"record.publish": KEEP_FOREVER}})


def test_expired_disappear_and_kept_remain(app, db, service, keep_publish_forever):
    """Expired events vanish from both stores; kept events stay searchable.

    A barren expired month is deleted, while a month sharing an expired event with
    a kept-forever event is swapped for a copy holding only that event.
    """
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        barren = _months_before(month_start, 25)  # only an expired draft.create
        mixed = _months_before(month_start, 20)  # expired draft + kept-forever publish
        recent = _months_before(month_start, 2)  # within the 13-month default

        ids = {
            "barren_draft": _make_event(service, "draft.create", barren, "os-barren"),
            "mixed_draft": _make_event(
                service, "draft.create", mixed, "os-mixed-draft"
            ),
            "mixed_publish": _make_event(
                service, "record.publish", mixed, "os-mixed-publish"
            ),
            "recent_draft": _make_event(service, "draft.create", recent, "os-recent"),
        }
        service.indexer.refresh()

        delete_expired_audit_logs()
        current_search_client.indices.refresh(
            index=build_alias_name("auditlog-*"), ignore=[404]
        )

        # PostgreSQL keeps exactly the kept events.
        assert _pg_ids() == {ids["mixed_publish"], ids["recent_draft"]}

        # Expired events are no longer searchable.
        assert _found(service, "os-barren", "draft.create") == 0
        assert _found(service, "os-mixed-draft", "draft.create") == 0
        # Kept-forever and within-period events remain searchable.
        assert _found(service, "os-mixed-publish", "record.publish") == 1
        assert _found(service, "os-recent", "draft.create") == 1

        # The barren month index is deleted; the mixed month name is now an alias.
        assert _concrete(_month_index(barren)) is None
        copy = _concrete(_month_index(mixed))
        assert copy.startswith(_month_index(mixed) + "-")
        assert current_search_client.count(index=copy)["count"] == 1


def test_month_name_follows_each_copy(app, db, service, set_app_config_fn_scoped):
    """Writes through the month name reach the copy, and a second clean moves it.

    The first run deletes ``draft.create`` from the month. A later run, with
    ``record.publish`` shortened and ``draft.create`` kept forever, deletes the
    publish and keeps a draft written after the first run. Stale copies left by a
    run that died before its swap are deleted.
    """
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month = _months_before(now, 30)
        name = _month_index(month)
        set_app_config_fn_scoped(
            {"AUDIT_LOGS_RETENTION": {"record.publish": KEEP_FOREVER}}
        )
        _make_event(service, "draft.create", month, "os-follow-old")
        _make_event(service, "record.publish", month, "os-follow-publish")
        service.indexer.refresh()

        delete_expired_audit_logs()
        first = _concrete(name)
        assert first.startswith(name + "-")

        # A write routed to the month name lands in the copy.
        _make_event(service, "draft.create", month, "os-follow-new")
        service.indexer.refresh()
        assert current_search_client.count(index=first)["count"] == 2

        stale = f"{name}-19990101000000"
        current_search_client.indices.create(index=stale)

        set_app_config_fn_scoped(
            {
                "AUDIT_LOGS_RETENTION": {
                    "record.publish": 24,
                    "draft.create": KEEP_FOREVER,
                }
            }
        )
        delete_expired_audit_logs()
        second = _concrete(name)
        assert second.startswith(name + "-")
        assert second != first
        assert _concrete(first) is None
        assert _concrete(stale) is None
        assert _found(service, "os-follow-publish", "record.publish") == 0
        assert _found(service, "os-follow-old", "draft.create") == 0
        assert _found(service, "os-follow-new", "draft.create") == 1


def test_run_under_index_prefix(app, db, service, set_app_config_fn_scoped):
    """With ``SEARCH_INDEX_PREFIX`` set, the copy and aliases carry the prefix."""
    client = current_search_client
    with app.app_context():
        set_app_config_fn_scoped(
            {
                "SEARCH_INDEX_PREFIX": "retention-pfx-",
                "AUDIT_LOGS_RETENTION": {"record.publish": KEEP_FOREVER},
            }
        )
        list(current_search.put_index_templates())
        try:
            month = _months_before(datetime.now(UTC).replace(tzinfo=None), 20)
            name = _month_index(month)
            assert name.startswith("retention-pfx-auditlog-")
            _make_event(service, "draft.create", month, "os-pfx-draft")
            _make_event(service, "record.publish", month, "os-pfx-publish")
            service.indexer.refresh()

            delete_expired_audit_logs()
            service.indexer.refresh()

            copy = _concrete(name)
            assert copy.startswith(name + "-")
            assert set(client.indices.get_alias(index=copy)[copy]["aliases"]) == {
                name,
                "retention-pfx-auditlog",
                "retention-pfx-audit-log",
            }
            assert _found(service, "os-pfx-draft", "draft.create") == 0
            assert _found(service, "os-pfx-publish", "record.publish") == 1
        finally:
            client.indices.delete(index="retention-pfx-auditlog*", ignore=[404])
            client.indices.delete_index_template(
                name="retention-pfx-auditlogs-*", ignore=[404]
            )


@pytest.fixture()
def drop_copies():
    """Make new month copies drop every document they are sent.

    A higher-priority template matches only copy names (``auditlog-YYYY-MM-*``), so
    the reindex reports no failures while the copy stays empty.
    """
    client = current_search_client
    pipeline = build_alias_name("retention-test-drop")
    template = build_alias_name("retention-test-drop")
    client.ingest.put_pipeline(id=pipeline, body={"processors": [{"drop": {}}]})
    client.indices.put_index_template(
        name=template,
        body={
            "index_patterns": [build_alias_name("auditlog-*-*-*")],
            "priority": 100,
            "template": {
                "settings": {"index.default_pipeline": pipeline},
                "aliases": {
                    build_alias_name("auditlog"): {},
                    build_alias_name("audit-log"): {},
                },
            },
        },
    )
    yield
    client.indices.delete_index_template(name=template, ignore=[404])
    client.ingest.delete_pipeline(id=pipeline, ignore=[404])


def test_copy_count_mismatch_stops_before_swap(
    app, db, service, keep_publish_forever, drop_copies
):
    """A copy missing documents raises; the old month stays and PostgreSQL is kept."""
    with app.app_context():
        month = _months_before(datetime.now(UTC).replace(tzinfo=None), 20)
        name = _month_index(month)
        draft = _make_event(service, "draft.create", month, "os-short-draft")
        publish = _make_event(service, "record.publish", month, "os-short-publish")
        service.indexer.refresh()

        with pytest.raises(RuntimeError, match="holds 0 documents, expected 1"):
            delete_expired_audit_logs()
        service.indexer.refresh()

        assert _concrete(name) == name
        assert _found(service, "os-short-draft", "draft.create") == 1
        assert _found(service, "os-short-publish", "record.publish") == 1
        (copy,) = current_search_client.indices.get(index=f"{name}-*")
        aliases = current_search_client.indices.get_alias(index=copy)[copy]["aliases"]
        assert aliases == {}
        assert _pg_ids() == {draft, publish}
        assert db.session.query(RetentionRun).count() == 0


def test_next_run_finishes_after_crash_between_steps(
    app, db, service, keep_publish_forever
):
    """Search cleaned but PostgreSQL not: the next run deletes the rows left behind."""
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month = _months_before(now, 20)
        draft = _make_event(service, "draft.create", month, "os-crash-draft")
        publish = _make_event(service, "record.publish", month, "os-crash-publish")
        service.indexer.refresh()

        # The search step of a run that died before its PostgreSQL step.
        _delete_from_opensearch({"draft.create": _months_before(now, 13)}, now)
        service.indexer.refresh()
        assert _found(service, "os-crash-draft", "draft.create") == 0
        assert _pg_ids() == {draft, publish}
        copy = _concrete(_month_index(month))

        assert delete_expired_audit_logs() == {"draft.create": 1}
        service.indexer.refresh()

        assert _pg_ids() == {publish}
        # Search had nothing left to delete, so the copy is not replaced.
        assert _concrete(_month_index(month)) == copy
        assert _found(service, "os-crash-publish", "record.publish") == 1
