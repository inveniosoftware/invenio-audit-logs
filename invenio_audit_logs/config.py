# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Configuration for invenio-audit-logs."""

from invenio_records_resources.services.records.facets import TermsFacet

from .proxies import current_audit_logs_actions_registry

AUDIT_LOGS_SEARCH = {
    "facets": ["resource", "user", "action_name"],
    "sort": [
        "bestmatch",
        "newest",
        "oldest",
    ],
}
"""Search configuration for audit logs."""

AUDIT_LOGS_FACETS = {
    "resource": dict(
        facet=TermsFacet(
            field="resource.type",
            label="Resource",
            value_labels={
                "record": "Record",
                "community": "Community",
            },
        ),
        ui=dict(field="resource.type"),
    ),
    "action_name": dict(
        facet=TermsFacet(
            field="action",
            label="Action",
            value_labels=lambda keys: {
                k: current_audit_logs_actions_registry[k].name for k in keys
            },
        ),
        ui=dict(field="action"),
    ),
    "user": dict(
        facet=TermsFacet(
            field="user.id",
            label="User",
            value_labels=lambda ids: {id: id.upper() for id in ids},
        ),
        ui=dict(field="user.id"),
    ),
}

AUDIT_LOGS_SORT_OPTIONS = {
    "bestmatch": dict(title="Best match", fields=["_score"]),
    "newest": dict(title="Newest", fields=["-@timestamp"]),
    "oldest": dict(title="Oldest", fields=["@timestamp"]),
}
"""Sort options for audit logs."""

AUDIT_LOGS_ENABLED = True
"""Feature flag. Disabled by default due to experimental nature of the APIs. Feature is not fully stable."""
