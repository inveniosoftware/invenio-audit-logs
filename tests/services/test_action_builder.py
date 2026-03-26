# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Test audit log builder."""

import pytest
from flask import g
from flask_login import login_user
from invenio_access.permissions import system_identity
from invenio_records_resources.services.uow import UnitOfWork
from mock_module.auditlog.actions import DraftCreateAuditLog, RecordPublishAuditLog

from invenio_audit_logs.services import AuditLogOp


def test_audit_log_builder(app, client_with_login, current_user, db, service):
    """Should succeed when creating an audit log via AuditLogAction using unit of work."""
    login_user(current_user, force=True)
    with app.test_request_context():
        with UnitOfWork(db.session) as uow:
            # Create the audit log
            op = AuditLogOp(
                DraftCreateAuditLog.build(
                    identity=g.identity,
                    resource_id="efgh-5678",
                ),
            )
            uow.register(op)
            uow.commit()

    # Read the created audit log
    result = service.read(
        identity=system_identity,
        id_=op.result["id"],
    )

    assert result["action"] == "draft.create"
    assert result["resource"]["id"] == "efgh-5678"
    assert result["resource"]["type"] == "record"
    assert result["user"]["id"] == "1"

    service.record_cls.index.refresh()

    search_result = service.search(
        identity=system_identity,
        params={"q": "resource.id: efgh-5678 AND action: draft.create"},
    )
    assert search_result.total == 1


def test_audit_log_builder_with_metadata(
    app, client_with_login, current_user, db, service
):
    """Should succeed when creating an audit log via AuditLogAction using unit of work with metadata."""
    login_user(current_user, force=True)
    with app.test_request_context():
        with UnitOfWork(db.session) as uow:
            # Create the audit log
            op = AuditLogOp(
                RecordPublishAuditLog.build(
                    identity=g.identity,
                    resource_id="efgh-5678",
                    parent_pid="parent-1234",
                    revision_id=9,
                ),
            )
            uow.register(op)
            uow.commit()

    # Read the created audit log
    result = service.read(
        identity=system_identity,
        id_=op.result["id"],
    )

    assert result["action"] == "record.publish"
    assert result["resource"]["id"] == "efgh-5678"
    assert result["resource"]["type"] == "record"
    assert result["user"]["id"] == "1"
    assert result["metadata"]["related_to"] == {"id": "parent-1234", "type": "parent"}
    assert result["metadata"]["revision_id"] == 9
    assert result["metadata"]["publishing_info"] == {
        "title": "Test Title",
        "created": "2026-01-01T12:00:00+00:00",
    }

    service.record_cls.index.refresh()

    # Search by nested fields
    search_result = service.search(
        identity=system_identity,
        params={
            "q": "metadata.related_to.id:parent-1234 AND metadata.revision_id:9 AND metadata.publishing_info.created:[2025-12-25T00:00:00 TO 2026-01-05T12:00:00]"
        },
    )
    assert search_result.total == 1

    # Search using range queries inside the `flat_object`
    search_result = service.search(
        identity=system_identity,
        params={
            "q": "metadata.publishing_info.created:[2025-12-25T00:00:00 TO 2026-01-01T00:00:00]"
        },
    )
    assert search_result.total == 0
