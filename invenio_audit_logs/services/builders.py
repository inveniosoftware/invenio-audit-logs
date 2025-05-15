# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit log data building utils."""

from abc import ABC

from flask import current_app


class AuditLogBuilder(ABC):
    """Audit log builder for audit operations."""

    context = None

    action = None
    resource_type = None
    message_template = None

    @classmethod
    def build(cls, resource, action, identity, **kwargs):
        """Build and register the audit log operation."""

        if not current_app.config.get("AUDIT_LOGS_ENABLED", False):
            return

        data = {
            "action": action,
            "resource": resource,
            "user": identity.id,
            "user_id": str(identity.id),
            "resource_type": resource["type"],
        }
        data = cls.resolve_context(cls, data, **kwargs)
        return data

    def resolve_context(self, data, **kwargs):
        """Resolve the context using the provided data."""
        NotImplementedError("The context resolver is not implemented for this action.")

    def render_message(self, data):
        """Render the message using the provided data."""
        return self.message_template.format(**data)

    def __str__(self):
        """Return str(self)."""
        # Value used by marshmallow schemas to represent the type.
        return self.action

    def __repr__(self):
        """Return repr(self)."""
        return f"<AuditLogBuilder '{self.action}'>"
