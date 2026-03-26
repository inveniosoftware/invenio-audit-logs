# -*- coding: utf-8 -*-
#
# Copyright (C) 2025-2026 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Action registration via entrypoint function."""

import marshmallow as ma

from invenio_audit_logs.services import AuditLogAction
from invenio_audit_logs.services.schema import ResourceSchema

from .context import RecordContext, UserContext


class PublishingInfoSchema(ma.Schema):
    """Publishing information schema."""

    title = ma.fields.Str(required=True)
    created = ma.fields.Str(
        required=True
    )  # SQLalchemy JSON field does not support DateTime during serialization


class DraftCreateAuditLog(AuditLogAction):
    """Audit log for draft creation."""

    id = "draft.create"
    resource_type = "record"

    message_template = ("User {user_id} created the draft {resource_id}.",)

    context = [
        UserContext(),
    ]


class RecordPublishAuditLog(DraftCreateAuditLog):
    """Audit log for record publication."""

    id = "record.publish"

    message_template = ("User {user_id} published the record {resource_id}.",)

    metadata_schema = {
        "related_to": ma.fields.Nested(
            ResourceSchema,
            required=True,
        ),
        "revision_id": ma.fields.Int(required=True),
        "publishing_info": ma.fields.Nested(
            PublishingInfoSchema,
            required=True,
            metadata={
                "description": "Publishing information.",
            },
        ),
    }

    context = DraftCreateAuditLog.context + [RecordContext()]
