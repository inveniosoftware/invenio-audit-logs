# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration.

See https://pytest-invenio.readthedocs.io/ for documentation on which test
fixtures are available.
"""

import pytest
from flask_principal import Identity, UserNeed
from flask_security import login_user
from invenio_access.permissions import authenticated_user, system_user_id
from invenio_accounts.testutils import login_user_via_session
from invenio_app.factory import create_api
from invenio_search import current_search

from invenio_audit_logs.proxies import current_audit_logs_service


@pytest.fixture(scope="module")
def create_app(instance_path, entry_points):
    """Application factory fixture."""
    return create_api


@pytest.fixture(autouse=True)
def setup_index_templates(app):
    """Setup index templates."""
    list(current_search.put_index_templates())


@pytest.fixture
def service(appctx):
    """Fixture for the current service."""
    return current_audit_logs_service


@pytest.fixture(scope="function")
def authenticated_identity():
    """Authenticated identity fixture."""
    identity = Identity(100)
    identity.provides.add(UserNeed(100))
    identity.provides.add(authenticated_user)
    return identity


@pytest.fixture(scope="function")
def resource_data():
    """Sample data."""
    return dict(
        action="draft.create",
        resource=dict(
            type="record",
            id="abcd-1234",
        ),
        resource_type="record",
        message=f" created the draft.",
        user=dict(
            id="1",
            username="User",
            email="current@inveniosoftware.org",
        ),
        user_id="1",
    )


@pytest.fixture()
def system_user():
    """System user."""
    return {
        "id": system_user_id,
        "username": "System",
        "email": "noreply@inveniosoftware.org",
    }


@pytest.fixture()
def current_user(app, db):
    """Users."""
    with db.session.begin_nested():
        datastore = app.extensions["security"].datastore
        user = datastore.create_user(
            email="current@inveniosoftware.org",
            password="123456",
            username="User",
            user_profile={
                "full_name": "User",
                "affiliations": "CERN",
            },
            active=True,
        )
    db.session.commit()
    return user


@pytest.fixture()
def client_with_login(client, current_user):
    """Log in a user to the client."""
    login_user(current_user, remember=True)
    login_user_via_session(client, email=current_user.email)
    return client
