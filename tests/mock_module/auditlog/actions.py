# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Action registration via entrypoint function."""

from invenio_audit_logs.services import AuditLogAction


class DraftCreateAuditLog(AuditLogAction):
    """Audit log for draft creation."""

    id = "draft.create"
    resource_type = "record"

    message_template = ("User {user_id} created the draft {resource_id}.",)

    def resolve_context(self, data, **kwargs):
        """Resolve the context using the provided data."""
        # This is just a placeholder implementation.
        data["user"] = dict(
            id="1",
            username="User",
            email="current@inveniosoftware.org",
        )
        return data
