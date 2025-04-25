# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more details.

"""Invenio OpenSearch Datastream Schema."""

from datetime import datetime

from invenio_access.permissions import system_identity
from marshmallow import EXCLUDE, Schema, fields, pre_dump, pre_load


class UserSchema(Schema):
    """User schema for logging."""

    name = fields.Str(required=False, description="User name (if available).")
    email = fields.Email(required=True, description="User email.")


class MetadataSchema(Schema):
    """Metadata schema for logging."""

    ip_address = fields.Str(
        required=False,
        description="IP address of the client.",
    )
    session = fields.Str(
        required=False,
        description="Session identifier.",
    )
    request_id = fields.Str(
        required=False,
        description="Unique identifier for the request.",
    )


class AuditLogJsonSchema(Schema):
    """Metadata schema for audit log events (JSON Field)."""

    resource_id = fields.Str(
        required=True, description="Unique identifier of the resource."
    )
    message = fields.Str(
        required=False,
        description="Human-readable description of the event.",
    )
    user = fields.Nested(
        UserSchema,
        required=False,
        description="Information about the user who triggered the event.",
    )
    metadata = fields.Nested(
        MetadataSchema,
        required=False,
        description="Additional structured metadata for logging.",
    )


class AuditLogSchema(Schema):
    """Main schema for audit log events in InvenioRDM."""

    class Meta:
        """Meta class to ignore unknown fields."""

        unknown = EXCLUDE  # Ignore unknown fields

    id = fields.Str(
        description="Unique identifier of the audit log event.",
    )
    created = fields.DateTime(
        required=True,
        description="Timestamp when the event occurred.",
        attribute="@timestamp",
    )
    action = fields.Str(
        required=True,
        description="The action that took place (e.g., record.create, community.update).",
    )
    resource_type = fields.Str(
        required=True,
        description="Type of resource (e.g., record, community, user).",
    )
    user_id = fields.Str(
        required=True,
        description="ID of the user who triggered the event.",
    )
    json = fields.Nested(
        AuditLogJsonSchema,
        required=True,
        description="Structured metadata for the audit log event.",
    )

    @pre_load
    def _mapping_to_internal_repr(self, json, **kwargs):
        """Remap fields before mapping to internal representation."""
        if "metadata" in self.context:
            metadata = self.context.pop("metadata")
            user = metadata.pop("user_account")
            if user:
                json["user_id"] = str(user.id)
                json["user"] = {"email": user.email}
                if user.username:
                    json["user"]["name"] = user.username
            else:
                json["user_id"] = system_identity.id
            json["metadata"] = metadata
        data = {
            "created": datetime.now().isoformat(),
            "action": json.pop("action"),
            "user_id": json.pop("user_id"),
            "resource_type": json.pop("resource_type"),
            "json": json.copy(),
        }
        return data

    @pre_dump
    def _mapping_from_internal_repr(self, obj, **kwargs):
        """Set json field for schema validation."""
        setattr(obj, "json", obj)
        if getattr(obj, "model", None):  # From DB
            timestamp = obj.model.created
        elif getattr(obj, "@timestamp"):  # From Search
            timestamp = datetime.fromisoformat(getattr(obj, "@timestamp"))
        else:
            return obj  # Let marshmallow's required field error handle this
        setattr(obj, "@timestamp", timestamp)
        return obj
