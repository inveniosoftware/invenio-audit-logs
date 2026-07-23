# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-License-Identifier: MIT

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
from sqlalchemy import MetaData, PrimaryKeyConstraint, text
from sqlalchemy.schema import CreateTable, DropTable

from invenio_audit_logs.proxies import current_audit_logs_service
from invenio_audit_logs.records.models import AuditLog


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


@pytest.fixture()
def partition_audit_table(db):
    """Re-create ``audit_logs_metadata`` as a partitioned table built from the model.

    PostgreSQL decides partitioning when the table is created, and the model does not
    say anything about partitioning (and should not). So this drops the plain table
    and builds it again from the model's own columns, adding only the partitioning
    parts: the ``PARTITION BY`` clause, the primary key (which has to include the
    partition key), and the child partitions. Because the columns come from the
    model, the test never repeats the schema and stays in sync with the model. It all
    runs in the test's transaction, so the table goes back to normal when the test
    ends.

    ``children`` maps each child partition name to its ``(from, to)`` range. Pass
    ``primary_key`` when the partition key has to be part of the primary key (which
    PostgreSQL requires); leave it out to keep the model's primary key.
    """
    if db.engine.name != "postgresql":
        pytest.skip("Partitioning only runs on PostgreSQL")

    def _partition(partition_by, children, primary_key=None):
        clone = AuditLog.__table__.to_metadata(MetaData())
        if primary_key is not None:
            clone.constraints = {
                c for c in clone.constraints if not isinstance(c, PrimaryKeyConstraint)
            }
            clone.append_constraint(PrimaryKeyConstraint(*primary_key))
        clone.dialect_options["postgresql"]["partition_by"] = partition_by

        db.session.execute(DropTable(AuditLog.__table__))
        db.session.execute(CreateTable(clone))
        for name, (start, end) in children.items():
            db.session.execute(
                text(
                    f"CREATE TABLE {name} PARTITION OF audit_logs_metadata "
                    f"FOR VALUES FROM ('{start}') TO ('{end}')"
                )
            )
        db.session.commit()

    return _partition


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
