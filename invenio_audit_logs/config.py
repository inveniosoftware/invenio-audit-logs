# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-License-Identifier: MIT

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

AUDIT_LOGS_ENABLED_ACTIONS = None
"""
Allow-list of actions to include in the audit logs.

``None`` (the default) allows all registered actions. Set it to a set of action
names to log only those; any other action is skipped. An action in
``AUDIT_LOGS_DISABLED_ACTIONS`` is never logged, even if you list it here.
To find all the available actions, check the entry points in the `invenio_audit_logs.actions` group.
```python
>>> from invenio_base.utils import entry_points
>>> [ep.name for ep in entry_points(group="invenio_audit_logs.actions")]
```
"""

AUDIT_LOGS_DISABLED_ACTIONS = set()
"""
Deny-list of actions to be excluded from the audit logs.
To find all the available actions, check the entry points in the `invenio_audit_logs.actions` group.
```python
>>> from invenio_base.utils import entry_points
>>> [ep.name for ep in entry_points(group="invenio_audit_logs.actions")]
```
"""
