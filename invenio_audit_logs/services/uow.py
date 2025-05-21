# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Unit of work operations for audit logs."""

from invenio_access.permissions import system_identity
from invenio_records_resources.services.uow import Operation, RecordCommitOp

from ..proxies import current_audit_logs_service


class AuditLogOp(Operation):
    """Audit logging operation."""

    def __init__(self, data, identity=system_identity):
        """Initialize operation."""
        self.data = data
        self.identity = identity
        self.result = None

    def on_register(self, uow):
        """Register the operation."""
        self.result = current_audit_logs_service.create(
            data=self.data,
            identity=self.identity,
            uow=uow,  # It will persist the log when on_commit is triggered
        )


class AuditRecordCommitOp(RecordCommitOp):
    """Audit logging operation."""

    def on_commit(self, uow):
        """Run the operation."""
        if self._indexer is not None:
            arguments = {"refresh": True} if self._index_refresh else {}
            return self._indexer.create(self._record, arguments)
