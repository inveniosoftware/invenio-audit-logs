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
from mock_module.auditlog.actions import DraftCreateAuditLog

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
