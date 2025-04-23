# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

from dataclasses import dataclass
from typing import Dict, Callable, Optional


@dataclass(frozen=True)
class AuditAction:
    """
    Represents an action for auditing purposes.

    Attributes:
        name (str): The name of the action.
        message_template (str): The template for the action's message.
        link_templates (Optional[Dict[str, Callable[[str], str]]]): Optional dictionary of link templates.

    Methods:
        render_message(data): Renders the message template with the provided data.
        generate_links(ids): Generates links using the link templates and the provided ids.

    Input Format Example:
    {
        "draft.create": AuditAction(
            name="draft.create",
            message_template="User {user_id} created the draft {resource_id}.",
            link_templates=lambda id: f"/uploads/{id}"
        ),
        "draft.edit": AuditAction(
            name="draft.edit",
            message_template="User {user_id} updated the draft {resource_id}.",
            link_templates=lambda id: f"/uploads/{id}"
        ),
        "record.publish": AuditAction(
            name="record.publish",
            message_template="User {user_id} published the record {resource_id}.",
            link_templates=lambda id: f"/records/{id}"
        ),
    }
    """

    name: str
    message_template: str
    link_templates: Optional[Dict[str, Callable[[str], str]]] = None

    def render_message(self, data):
        """Render the message using the provided data."""
        return self.message_template.format(**data)
