# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-License-Identifier: MIT

"""Module providing audit logging features for Invenio.."""

from invenio_base.utils import entry_points

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
        self.validate_actions_config(app)
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
        """Action loading registry."""
        self.actions_registry = {}
        self.schema_cache = {}
        for ep in entry_points(group="invenio_audit_logs.actions"):
            action = ep.load()
            action_name = action.id
            self.actions_registry[action_name] = action
            self.schema_cache[action_name] = action.marshmallow_schema()

    def validate_actions_config(self, app):
        """Check the action allow/deny lists against the registry."""
        known = set(self.actions_registry)
        enabled = set(app.config.get("AUDIT_LOGS_ENABLED_ACTIONS") or set())
        disabled = set(app.config.get("AUDIT_LOGS_DISABLED_ACTIONS") or set())

        unknown = (enabled | disabled) - known
        if unknown:
            raise RuntimeError(
                f"Unknown audit log actions configured: {sorted(unknown)}. "
                f"Registered actions are: {sorted(known)}."
            )

        overlap = enabled & disabled
        if overlap:
            raise RuntimeError(
                f"Audit log actions {sorted(overlap)} are in both "
                "AUDIT_LOGS_ENABLED_ACTIONS and AUDIT_LOGS_DISABLED_ACTIONS. "
                "An action cannot be both allowed and denied."
            )
