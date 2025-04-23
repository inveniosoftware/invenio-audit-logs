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
from marshmallow import (
    EXCLUDE,
    Schema,
    fields,
    post_load,
    pre_dump,
    pre_load,
)

from ..proxies import current_audit_logs_actions_registry


class UserSchema(Schema):
    """User schema for logging."""

    id = fields.Str(
        required=True,
        description="ID of the user who triggered the event.",
    )
    name = fields.Str(
        required=False,
        description="User name (if available).",
    )
    email = fields.Email(
        required=False,
        description="User email.",
    )  # TODO: Make required after figuring out system user


class ResourceSchema(Schema):
    """Resource schema for logging."""

    type = fields.Str(
        required=True,
        description="Type of resource (e.g., record, community, user).",
    )
    id = fields.Str(
        required=True,
        description="Unique identifier of the resource.",
    )


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
    resource = fields.Nested(
        ResourceSchema,
        required=True,
        description="Type of resource (e.g., record, community, user).",
    )
    user = fields.Nested(
        UserSchema,
        required=True,
        description="Information about the user who triggered the event.",
    )
    metadata = fields.Nested(
        MetadataSchema,
        required=False,
        description="Additional structured metadata for logging.",
    )

    @pre_load
    def _add_user_context(self, json, **kwargs):
        """Remap fields before mapping to internal representation."""
        if "metadata" in self.context:
            metadata = self.context.get("metadata")
            user = metadata.pop("user_account")
            if user:
                json["user"] = {"id": str(user.id), "email": user.email}
                if user.username:
                    json["user"]["name"] = user.username
            else:
                json["user"] = {"id": system_identity.id}
        json["metadata"] = metadata
        json["created"] = datetime.now().isoformat()
        return json

    @post_load
    def _lift_up_fields(self, json, **kwargs):
        """Lift up nested fields for DB insert."""
        json["user_id"] = json["user"].get("id")
        json["resource_type"] = json["resource"].get("type")
        return json

    @pre_dump
    def _add_timestamp(self, obj, **kwargs):
        """Set json field for schema validation."""
        if getattr(obj, "model", None):  # From DB
            timestamp = obj.model.created
        elif getattr(obj, "@timestamp"):  # From Search
            timestamp = datetime.fromisoformat(getattr(obj, "@timestamp"))
        else:
            return obj  # Let marshmallow's required field error handle this
        setattr(obj, "@timestamp", timestamp)
        return obj

    @validates_schema
    def validate_action_for_resource(self, data, **kwargs):
        """Validates the action for a given resource type."""
        resource_type = data["resource_type"]
        action = data["action"]

        if not resource_type or not action:
            return

        valid_actions = current_audit_logs_actions_registry.get(resource_type)

        if action not in valid_actions.keys():
            raise ValidationError(
                {
                    "action": f"Invalid action '{action}' for resource type '{resource_type}'."
                }
            )
