# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o.
# SPDX-License-Identifier: MIT
"""Test audit log service."""

import pytest
from flask_login import login_user
from invenio_access.permissions import system_identity
from invenio_records_resources.services.errors import PermissionDeniedError
from mock_module.auditlog.components import CallTrackingComponent


def test_audit_log_create(
    app,
    service,
    resource_data,
    client_with_login,
    current_user,
):
    """Should succeed when identity matches g.identity."""
    login_user(current_user, force=True)

    CallTrackingComponent.reset()
    with app.test_request_context():
        result = service.create(
            identity=system_identity,
            data=resource_data,
        )
    assert CallTrackingComponent.create_called

    CallTrackingComponent.reset()
    result = service.read(
        identity=system_identity,
        id_=result.id,
    )
    assert CallTrackingComponent.read_called

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
    expected_links = {
        "self": f"https://127.0.0.1:5000/api/audit-logs/{result.id}",
    }
    assert expected_links == result["links"]

    # Search
    service.record_cls.index.refresh()
    search_result = service.search(
        identity=system_identity,
        params={"q": "resource.id: abcd-1234 AND action: draft.create"},
    )
    assert search_result.total == 1
    expected_links = {
        "self": (
            "https://127.0.0.1:5000/api/audit-logs/?"
            "page=1&q=resource.id:+abcd-1234+AND+action:+draft.create"
            "&size=20&sort=newest"
        )
    }
    data = search_result.to_dict()
    assert expected_links == data["links"]


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


def test_audit_log_config_disabled(
    app, service, resource_data, system_user, monkeypatch
):
    """Should succeed when config is set."""
    monkeypatch.setitem(app.config, "AUDIT_LOGS_ENABLED", False)
    resource_data["user"] = system_user
    with app.test_request_context():
        result = service.create(
            identity=system_identity,
            data=resource_data,
        )
    assert result is None

    monkeypatch.setitem(app.config, "AUDIT_LOGS_ENABLED", True)
    monkeypatch.setitem(
        app.config, "AUDIT_LOGS_DISABLED_ACTIONS", set(["draft.create"])
    )
    with app.test_request_context():
        result = service.create(
            identity=system_identity,
            data=resource_data,
        )
    assert result is None
