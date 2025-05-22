# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Test audit log service."""

import pytest
from flask import g
from flask_login import login_user
from invenio_access.permissions import system_identity
from invenio_records_resources.services.errors import PermissionDeniedError


def test_audit_log_create(
    app,
    service,
    resource_data,
    client_with_login,
    current_user,
):
    """Should succeed when identity matches g.identity."""
    login_user(current_user, force=True)

    with app.test_request_context():
        result = service.create(
            identity=system_identity,
            data=resource_data,
        )

    result = service.read(
        identity=system_identity,
        id_=result.id,
    )

    assert result["action"] == "draft.create"
    assert result["resource"] == {
        "id": "abcd-1234",
        "type": "record",
    }
    assert result["user"] == {
        "id": "1",
        "username": "User",
        "email": "current@inveniosoftware.org",
    }

    service.record_cls.index.refresh()

    search_result = service.search(
        identity=system_identity,
        params={"q": "resource.id: abcd-1234 AND action: draft.create"},
    )
    assert search_result.total == 1


def test_audit_log_create_identity_mismatch(
    app, service, resource_data, client_with_login, authenticated_identity
):
    """Should fail when identity != g.identity."""
    with app.test_request_context():
        with pytest.raises(PermissionDeniedError):
            service.create(
                identity=authenticated_identity,  # Different identity
                data=resource_data,
            )


def test_audit_log_create_system_identity(app, service, system_user, resource_data):
    """Should succeed when identity is system."""
    resource_data["user"] = system_user
    with app.test_request_context():
        result = service.create(
            identity=system_identity,
            data=resource_data,
        )

    result = service.read(
        identity=system_identity,
        id_=result.id,
    )

    assert result["action"] == "draft.create"
    assert result["resource"] == {
        "id": "abcd-1234",
        "type": "record",
    }
    assert result["user"] == system_user

    service.record_cls.index.refresh()

    search_result = service.search(
        identity=system_identity,
        params={"q": "user.id: system AND action: draft.create"},
    )
    assert search_result.total == 1
