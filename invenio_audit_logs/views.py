# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""View functions for audit logs API."""

from flask import Blueprint

blueprint = Blueprint("invenio_audit_logs", __name__)


def create_audit_logs_blueprint(app):
    """Create app blueprint."""
    ext = app.extensions["invenio-audit-logs"]
    return ext.audit_log_resource.as_blueprint()
