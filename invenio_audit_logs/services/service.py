# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit Logs Service API."""

from datetime import datetime

from invenio_records_resources.services.records import RecordService
from invenio_records_resources.services.uow import unit_of_work

from .uow import AuditLogOp


class AuditLogService(RecordService):
    """Audit log service layer."""

    @unit_of_work()
    def create(self, identity, data, raise_errors=True, uow=None):
        """Create a record.

        :param identity: Identity of user creating the record.
        :param dict data: Input data according to the data schema.
        :param bool raise_errors: raise schema ValidationError or not.
        :param dict uow: Unit of Work.
        """
        self.require_permission(identity, "create", user_identity=identity)

        if "created" not in data:
            data["created"] = datetime.now().isoformat()

        # The user and session data is populated via component
        self.run_components("create", identity=identity, data=data)

        # Validate data, action, resource_type and create record with id
        data, errors = self.schema.load(
            data,
            context={
                "identity": identity,
            },
            raise_errors=raise_errors,
        )
        log = self.record_cls.create(
            {},
            **data,
        )

        # Persist record (DB and index)
        uow.register(AuditLogOp(log, self.indexer))

        return self.result_item(
            self,
            identity,
            log,
            links_tpl=self.links_item_tpl,
            errors=errors,
        )

    def read(
        self,
        identity,
        id_,
        **kwargs,
    ):
        """Read a record."""
        self.require_permission(identity, "read", user_identity=identity)

        # Read the record
        log = self.record_cls.get_record(id_=id_)

        # Return the result
        return self.result_item(
            self,
            identity,
            log,
            links_tpl=self.links_item_tpl,
        )


class DisabledAuditLogService(AuditLogService):
    """Disabled Audit Log Service."""

    def create(self, *args, **kwargs):
        """Overridden create method."""
        return None
