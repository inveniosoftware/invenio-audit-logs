# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more details.

"""Invenio OpenSearch Datastream Schema."""

from datetime import datetime

from marshmallow import EXCLUDE, Schema, fields, post_load, pre_dump


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
        required=True,
        description="User email.",
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
    metadata = fields.Nested(
        MetadataSchema,
        required=False,
        description="Additional structured metadata for logging.",
    )

    user = fields.Nested(
        UserSchema,
        dump_only=True,
        required=True,
        description="Information about the user who triggered the event.",
    )

    @post_load
    def _lift_up_fields(self, json, **kwargs):
        """Lift up nested fields for DB insert."""
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
