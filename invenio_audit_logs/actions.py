# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Class for Audit Action registered via entrypoints."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditAction:
    """
    Represents an action for auditing purposes.

    Attributes:
        name (str): The name of the action.
        message_template (str): The template for the action's message.

    Methods:
        render_message(data): Renders the message template with the provided data.

    Input Format Example:
    {
        "draft.create": AuditAction(
            name="draft.create",
            message_template="User {user_id} created the draft {resource_id}.",
        ),
        "draft.edit": AuditAction(
            name="draft.edit",
            message_template="User {user_id} updated the draft {resource_id}.",
        ),
        "record.publish": AuditAction(
            name="record.publish",
            message_template="User {user_id} published the record {resource_id}.",
        ),
    }
    """

    name: str
    message_template: str

    def render_message(self, data):
        """Render the message using the provided data."""
        return self.message_template.format(**data)

    def __str__(self):
        """Return str(self)."""
        # Value used by marshmallow schemas to represent the type.
        return self.name

    def __repr__(self):
        """Return repr(self)."""
        return f"<AuditAction '{self.name}'>"
