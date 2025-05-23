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
from invenio_app.factory import create_api as _create_api


@pytest.fixture(scope="module")
def app_config(app_config):
    """Application config override."""
    app_config["THEME_FRONTPAGE"] = False
    app_config["AUDIT_LOGS_ENABLED"] = True
    return app_config


@pytest.fixture(scope="module")
def create_app(instance_path):
    """Application factory fixture."""
    return _create_api


@pytest.fixture(scope="module")
def extra_entry_points():
    """Register extra entry point."""
    return {
        "invenio_audit_logs.actions": [
            "draft.create = mock_module.auditlog.actions:DraftCreateAuditLog",
        ]
    }
