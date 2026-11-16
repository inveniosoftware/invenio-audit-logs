# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-License-Identifier: MIT

"""Configuration for invenio-audit-logs."""

from invenio_records_resources.services.records.facets import TermsFacet

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
            value_labels=lambda keys: {k: k.capitalize() for k in keys},
        ),
        ui=dict(field="resource.type"),
    ),
    "action_name": dict(
        facet=TermsFacet(
            field="action",
            label="Action",
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
"""Feature flag. Disabled by default."""

AUDIT_LOGS_DISABLED_ACTIONS = set()
"""
Disabled actions to be excluded from the audit logs.
To find all the available actions, check the entry points in the `invenio_audit_logs.actions` group.
```python
>>> from invenio_base.utils import entry_points
>>> [ep.name for ep in entry_points(group="invenio_audit_logs.actions")]
```
"""

AUDIT_LOGS_RETENTION_DEFAULT = 13
"""Retention in months for any action without an explicit entry below.

Finite on purpose: a new or unconfigured action is kept for this period rather
than forever by oversight. 13 months is a common security-log default. An event
is deleted once its calendar month is this many months before the current one, so
it is kept at least this many months and at most one month more.
"""

AUDIT_LOGS_RETENTION = {}
"""Per-action retention periods, keyed on the action id.

Each value is a number of months or the ``KEEP_FOREVER`` sentinel. Keeping an
action forever is the deliberate exception, e.g.::

    from invenio_audit_logs import KEEP_FOREVER

    AUDIT_LOGS_RETENTION = {
        "user.login": 2,
        "user.block": KEEP_FOREVER,
    }
"""

AUDIT_LOGS_RETENTION_BATCH_SIZE = 1000
"""Rows deleted per transaction when deleting expired events from PostgreSQL."""
