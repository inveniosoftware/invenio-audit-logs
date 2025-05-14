# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
# Copyright (C) 2025 Graz University of Technology.
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
        metadata={
            "description": "Type of resource (e.g., record, community, user).",
        },
    )
    id = fields.Str(
        required=True,
        metadata={
            "description": "Unique identifier of the resource.",
        },
    )


class MetadataSchema(Schema):
    """Metadata schema for logging."""

    ip_address = fields.Str(
        required=False,
        metadata={
            "description": "IP address of the client.",
        },
    )
    session = fields.Str(
        required=False,
        metadata={
            "description": "Session identifier.",
        },
    )
    request_id = fields.Str(
        required=False,
        metadata={
            "description": "Unique identifier for the request.",
        },
    )


class UserSchema(Schema):
    """User schema for logging."""

    id = fields.Str(
        required=True,
        metadata={
            "description": "ID of the user who triggered the event.",
        },
    )
    name = fields.Str(
        required=False,
        metadata={
            "description": "User name (if available).",
        },
    )
    email = fields.Email(
        required=True,
        metadata={
            "description": "User email.",
        },
    )


class AuditLogSchema(Schema):
    """Main schema for audit log events in InvenioRDM."""

    class Meta:
        """Meta class to ignore unknown fields."""

        unknown = EXCLUDE  # Ignore unknown fields

    id = fields.Str(
        metadata={
            "description": "Unique identifier of the audit log event.",
        }
    )
    created = fields.DateTime(
        required=True,
        metadata={
            "description": "Timestamp when the event occurred.",
        },
        attribute="@timestamp",
    )
    action = fields.Str(
        required=True,
        metadata={
            "description": "The action that took place (e.g., record.create, community.update).",
        },
    )
    resource = fields.Nested(
        ResourceSchema,
        required=True,
        metadata={
            "description": "Type of resource (e.g., record, community, user).",
        },
    )
    metadata = fields.Nested(
        MetadataSchema,
        required=False,
        metadata={
            "description": "Additional structured metadata for logging.",
        },
    )
    user = fields.Nested(
        UserSchema,
        required=True,
        metadata={
            "description": "Information about the user who triggered the event.",
        },
    )

    # Load only fields for DB insert
    user_id = fields.Str(
        required=True,
        description="ID of the user who triggered the event.",
        load_only=True,
    )
    resource_type = fields.Str(
        required=True,
        description="Type of resource (e.g., record, community, user).",
        load_only=True,
    )

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
