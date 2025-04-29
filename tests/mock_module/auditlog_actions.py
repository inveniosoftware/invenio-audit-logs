# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Action registration via entrypoint function."""

from invenio_audit_logs.actions import AuditAction


def record_actions():
    """Function to add actions to the registry."""
    return {
        "draft.create": AuditAction(
            name="draft.create",
            message_template="User {user_id} created the draft {resource_id}.",
        ),
    }
