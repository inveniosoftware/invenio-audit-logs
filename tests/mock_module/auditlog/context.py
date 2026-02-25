# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Audit log context resolvers."""

from invenio_records.dictutils import dict_set


class UserContext(object):
    """Audit log context for user."""

    def __call__(self, data, **kwargs):
        """Update data with resolved user data."""
        data["user"] = dict(
            id="1",
            username="User",
            email="current@inveniosoftware.org",
        )
        return data


class RecordContext(object):
    """Audit log context for record."""

    def __call__(self, data, **kwargs):
        """Update data with resolved record data."""
        revision_id = kwargs.get("revision_id")
        parent_pid = kwargs.get("parent_pid")
        dict_set(data, "metadata.revision_id", revision_id)
        dict_set(data, "metadata.parent_pid", parent_pid)
        return data
