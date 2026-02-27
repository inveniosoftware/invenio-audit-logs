# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit log data building utils."""

import marshmallow as ma
from flask import current_app

from .schema import AuditLogSchema, MetadataSchema


class AuditLogAction:
    """Audit log builder for audit operations."""

    context = []

    id = None
    resource_type = None

    metadata_schema = None
    metadata_required = True

    message_template = None

    @classmethod
    def build(cls, identity, resource_id, **kwargs):
        """Build and register the audit log operation."""
        if not current_app.config["AUDIT_LOGS_ENABLED"]:
            return

        data = {
            "action": cls.id,
            "resource": {"id": resource_id, "type": cls.resource_type},
            "user_id": str(identity.id),
            "resource_type": cls.resource_type,
        }
        cls.resolve_context(cls, data, **kwargs)
        return data

    def resolve_context(self, data, **kwargs):
        """Resolve the context using the provided data."""
        for context in self.context:
            context(data, **kwargs)

    @classmethod
    def marshmallow_schema(cls):
        """Create the entire audit log schema with the dynamically created metadata schema."""
        additional_fields = {}
        if cls.metadata_schema is not None:
            additional_fields["metadata"] = ma.fields.Nested(
                MetadataSchema.from_dict(cls.metadata_schema),
                required=cls.metadata_required,
                unknown=ma.EXCLUDE,  # Ignore unknown fields
            )

        # Dynamically create a schema from the additional metadata fields defined
        return AuditLogSchema.from_dict(additional_fields)

    def render_message(self, data):
        """Render the message using the provided data."""
        return self.message_template.format(**data)

    def __str__(self):
        """Return str(self)."""
        # Value used by marshmallow schemas to represent the type.
        return self.id

    def __repr__(self):
        """Return repr(self)."""
        return f"<AuditLogAction '{self.id}'>"
