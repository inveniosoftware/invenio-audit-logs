# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit log data building utils."""

from flask import current_app
from invenio_access.permissions import system_identity
from invenio_records.dictutils import dict_lookup, dict_set
from invenio_records_resources.references.entity_resolvers import ServiceResultResolver


class UserResolve:
    """Payload generator for audit log using the service result resolvers."""

    def __init__(self, key):
        """Ctor."""
        self.key = key

    def __call__(self, resolver, log_data):
        """Update required recipient information and add backend id."""
        entity_ref = dict_lookup(log_data, self.key)
        if entity_ref == system_identity.id:
            entity_data = {
                "id": str(system_identity.id),
                "name": "system",
                "email": "system@system.org",
            }
        else:
            entity = resolver.get_entity_proxy({self.key: entity_ref}).resolve()
            entity_data = {
                "id": str(entity["id"]),
                "name": entity["username"],
                "email": entity["email"],
            }
        dict_set(log_data, self.key, entity_data)


class AuditLogBuilder:
    """Audit log builder for audit operations."""

    context = [
        ServiceResultResolver(service_id="users", type_key="user"),
    ]

    action = None
    resource_type = None
    message_template = None

    @classmethod
    def build(cls, resource, action, identity):
        """Build and register the audit log operation."""

        if not current_app.config.get("AUDIT_LOGS_ENABLED", False):  # Fix later
            return

        data = {
            "action": action,
            "resource": resource,
            "user": identity.id,
            "user_id": str(identity.id),
            "resource_type": resource["type"],
        }
        data = cls.resolve_user_context(cls, data)
        return data

    def resolve_user_context(self, log_data):
        """Resolve all references in the audit log context."""
        for resolver in self.context:
            entity_resolver = UserResolve(resolver.type_key)
            entity_resolver(resolver, log_data)
        return log_data

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
