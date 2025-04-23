# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Unit of work operations for audit logs."""

from invenio_db.uow import Operation
from invenio_records_resources.services.uow import Operation


class AuditLogOp(Operation):
    """Audit logging operation."""

    def __init__(self, record, indexer, index_refresh=False):
        """Initialize the record commit operation."""
        self._record = record
        self._indexer = indexer
        self._index_refresh = index_refresh

    def on_register(self, uow):
        """Commit record (will flush to the database)."""
        self._record.commit()

    def on_commit(self, uow):
        """Run the operation."""
        arguments = {"refresh": True} if self._index_refresh else {}
        return self._indexer.create(self._record, arguments)
