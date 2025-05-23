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
    "facets": ["resource", "action_name"],
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
                k: current_audit_logs_actions_registry[k].id for k in keys
            },
        ),
        ui=dict(field="action"),
    ),
}

AUDIT_LOGS_SORT_OPTIONS = {
    "bestmatch": dict(title="Best match", fields=["_score"]),
    "newest": dict(title="Newest", fields=["-@timestamp"]),
    "oldest": dict(title="Oldest", fields=["@timestamp"]),
}
"""Sort options for audit logs."""

AUDIT_LOGS_ENABLED = False
"""Feature flag. Disabled by default due to experimental nature of the APIs. Feature is not fully stable."""

AUDIT_LOGS_METADATA_FIELDS = {
    "revision_id": True,
    "parent_pid": True,
    "ip_address": True,
    "session": True,
    "request_id": False,
}
"""Metadata fields to be included in the audit log."""
