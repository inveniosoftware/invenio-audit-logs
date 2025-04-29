# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Configuration for invenio-audit-logs."""

from invenio_records_resources.services.records.facets import TermsFacet

AUDIT_LOGS_SEARCH = {
    "facets": ["resource"],
    "sort": [
        "bestmatch",
        "newest",
        "oldest",
    ],
    # query_parser_cls
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
}

AUDIT_LOGS_SORT_OPTIONS = {
    "bestmatch": dict(title="Best match", fields=["_score"]),
    "newest": dict(title="Newest", fields=["-@timestamp"]),
    "oldest": dict(title="Oldest", fields=["@timestamp"]),
}
"""Sort options for audit logs."""
