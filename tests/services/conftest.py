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
from invenio_access.permissions import authenticated_user
from invenio_app.factory import create_api
from invenio_search import current_search


@pytest.fixture(scope="module")
def create_app(instance_path, entry_points):
    """Application factory fixture."""
    return create_api


@pytest.fixture(autouse=True)
def setup_index_templates(app):
    """Setup index templates."""
    list(current_search.put_index_templates())


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
        message=f" created the draft.",
    )


@pytest.fixture(scope="module")
def current_user(UserFixture, app, database):
    """Users."""
    user = UserFixture(
        email=f"current@inveniosoftware.org",
        password="123456",
        username="User",
        user_profile={
            "full_name": "User",
            "affiliations": "CERN",
        },
        active=True,
        confirmed=True,
    )
    user.create(app, database)
    # when using `database` fixture (and not `db`), commit the creation of the
    # user because its implementation uses a nested session instead
    database.session.commit()
    return user
