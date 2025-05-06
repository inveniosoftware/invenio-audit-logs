# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Unit of work operations for audit logs."""

from invenio_records_resources.services.uow import RecordCommitOp


class AuditRecordCommitOp(RecordCommitOp):
    """Audit logging operation."""

    def on_commit(self, uow):
        """Run the operation."""
        if self._indexer is not None:
            arguments = {"refresh": True} if self._index_refresh else {}
            return self._indexer.create(self._record, arguments)
