# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Module providing audit logging features for Invenio.."""

from importlib_metadata import entry_points

from . import config
from .resources import AuditLogResource, AuditLogResourceConfig
from .services import AuditLogService, AuditLogServiceConfig


class InvenioAuditLogs(object):
    """Invenio-Audit-Logs extension."""

    def __init__(self, app=None):
        """Extension initialization."""
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Flask application initialization."""
        self.init_config(app)
        self.init_services(app)
        self.init_resources(app)
        self.load_actions_registry()
        app.extensions["invenio-audit-logs"] = self

    def init_config(self, app):
        """Initialize configuration."""
        for k in dir(config):
            if k.startswith("AUDIT_LOGS_"):
                app.config.setdefault(k, getattr(config, k))

    def init_services(self, app):
        """Initialize services."""
        self.audit_log_service = AuditLogService(
            config=AuditLogServiceConfig.build(app),
        )

    def init_resources(self, app):
        """Init resources."""
        self.audit_log_resource = AuditLogResource(
            service=self.audit_log_service,
            config=AuditLogResourceConfig.build(app),
        )

    def load_actions_registry(self):
        self.actions_registry = {}
        for ep in entry_points(group="invenio_audit_logs.actions"):
            resource_type = ep.name
            resource_actions = ep.load()
            self.actions_registry.setdefault(resource_type, {})
            for action_name, action_factory in resource_actions().items():
                self.actions_registry[resource_type][action_name] = action_factory
