# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Jobs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Proxies."""

from flask import current_app
from werkzeug.local import LocalProxy

current_audit_logs_service = LocalProxy(
    lambda: current_app.extensions["invenio-audit-logs"].audit_log_service
)
"""Proxy to an instance of ``AuditLogs`` service."""

current_audit_logs_actions_registry = LocalProxy(
    lambda: current_app.extensions["invenio-audit-logs"].actions_registry
)
"""Proxy to an instance of ``AuditLogs`` action registry."""

current_audit_logs_resolvers = LocalProxy(
    lambda: current_app.extensions["invenio-audit-logs"].entity_resolvers
)
"""Proxy to an instance of ``AuditLogs`` entity resolver registry."""
