# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Test alembic recipes for Invenio-Audit-Logs."""

import pytest
from invenio_db.utils import alembic_test_context, drop_alembic_version_table


def test_alembic(base_app, database):
    """Test alembic recipes."""
    db = database
    ext = base_app.extensions["invenio-db"]

    if db.engine.name == "sqlite":
        raise pytest.skip("Upgrades are not supported on SQLite.")

    base_app.config["ALEMBIC_CONTEXT"] = alembic_test_context()

    # Check that this package's SQLAlchemy models have been properly registered
    assert "audit_logs_metadata" in db.metadata.tables

    # Check that Alembic agrees that there's no further tables to create.
    assert list(ext.alembic.compare_metadata()) == []

    # Drop everything and recreate tables all with Alembic
    db.drop_all()
    drop_alembic_version_table()
    ext.alembic.upgrade()
    assert list(ext.alembic.compare_metadata()) == []

    # Try to upgrade and downgrade
    ext.alembic.stamp()
    ext.alembic.downgrade(target="96e796392533")
    ext.alembic.upgrade()
    assert list(ext.alembic.compare_metadata()) == []

    drop_alembic_version_table()
