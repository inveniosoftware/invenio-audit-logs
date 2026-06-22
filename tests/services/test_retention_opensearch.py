# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Tests for the OpenSearch side of audit log retention.

The retention task deletes the search copy before PostgreSQL. A month with no
survivors has its whole ``auditlog-YYYY-MM`` index dropped; a month that still
holds survivors is rebuilt from PostgreSQL, the source of truth. No
``delete_by_query`` is used. These tests assert the external behaviour: which
events stay searchable after a run, that a barren month index is gone while a
month with survivors is a fresh index holding only them, and that the rebuild
reflects PostgreSQL rather than the index's prior contents.
"""

from datetime import datetime, timezone

import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_search import current_search_client
from invenio_search.utils import build_alias_name

from invenio_audit_logs import KEEP_FOREVER
from invenio_audit_logs.records.models import AuditLog
from invenio_audit_logs.tasks import delete_expired_audit_logs

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


def _index_uuid(name):
    """Return the OpenSearch uuid of index ``name``, or ``None`` if absent."""
    info = current_search_client.indices.get(index=name, ignore=[404])
    if name not in info:
        return None
    return info[name]["settings"]["index"]["uuid"]


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


@pytest.fixture()
def keep_publish_forever(set_app_config_fn_scoped):
    """Keep ``record.publish`` forever; everything else uses the 13-month default."""
    set_app_config_fn_scoped({"AUDIT_LOGS_RETENTION": {"record.publish": KEEP_FOREVER}})


def test_expired_disappear_and_survivors_remain(app, db, service, keep_publish_forever):
    """Expired events vanish from both stores; survivors stay searchable.

    A barren expired month is dropped outright, while a month sharing an expired
    event with a kept-forever survivor is rebuilt down to that survivor.
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
        service.record_cls.index.refresh()

        # The mixed month is rebuilt, so its index identity must change; the barren
        # month is dropped, so its index must be gone afterwards.
        mixed_uuid_before = _index_uuid(_month_index(mixed))

        delete_expired_audit_logs()
        current_search_client.indices.refresh(
            index=build_alias_name("auditlog-*"), ignore=[404]
        )

        # PostgreSQL keeps exactly the survivors.
        assert _pg_ids() == {ids["mixed_publish"], ids["recent_draft"]}

        # Expired events are no longer searchable.
        assert _found(service, "os-barren", "draft.create") == 0
        assert _found(service, "os-mixed-draft", "draft.create") == 0
        # Kept-forever and within-period events remain searchable.
        assert _found(service, "os-mixed-publish", "record.publish") == 1
        assert _found(service, "os-recent", "draft.create") == 1

        # The barren month index is deleted; the mixed month is a fresh index.
        assert _index_uuid(_month_index(barren)) is None
        mixed_uuid_after = _index_uuid(_month_index(mixed))
        assert mixed_uuid_after is not None
        assert mixed_uuid_after != mixed_uuid_before


def test_rebuild_reconciles_from_postgres(app, db, service, keep_publish_forever):
    """A rebuilt month mirrors PostgreSQL, not the index's earlier contents.

    Expired events are deleted from OpenSearch before PostgreSQL, and OpenSearch is rebuilt from it, so a document with
    no backing row is dropped even though, taken alone, it looks like a survivor.
    """
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month = _months_before(month_start, 30)

        # An expired draft triggers processing of the month; a kept-forever publish
        # is indexed alongside it and then removed from PostgreSQL only, leaving an
        # orphan that survives in OpenSearch until the rebuild reconciles the month.
        _make_event(service, "draft.create", month, "os-orphan-draft")
        orphan = _make_event(service, "record.publish", month, "os-orphan-publish")
        service.record_cls.index.refresh()

        db.session.query(AuditLog).filter(AuditLog.id == orphan).delete(
            synchronize_session=False
        )
        db.session.commit()
        # The orphan is still searchable before the run.
        assert _found(service, "os-orphan-publish", "record.publish") == 1

        delete_expired_audit_logs()
        current_search_client.indices.refresh(
            index=build_alias_name("auditlog-*"), ignore=[404]
        )

        # PostgreSQL holds nothing for this month, so the rebuilt search copy does
        # not either: the orphan is gone and the month index dropped entirely.
        assert _found(service, "os-orphan-draft", "draft.create") == 0
        assert _found(service, "os-orphan-publish", "record.publish") == 0
        assert _index_uuid(_month_index(month)) is None
