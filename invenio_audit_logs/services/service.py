# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit Logs Service API."""

from datetime import datetime

from invenio_access.permissions import system_identity
from invenio_accounts.proxies import current_datastore
from invenio_records_resources.services.records import RecordService
from invenio_records_resources.services.uow import unit_of_work

from .uow import AuditRecordCommitOp


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
        if not self.config.enabled:
            # don't create log if feature disabled
            return

        self.require_permission(identity, "create")
        if "created" not in data:
            data["created"] = datetime.utcnow().isoformat()

        # Validate data, action, resource_type and create record with id
        data, errors = self.schema.load(
            data,
            context={
                "identity": identity,
            },
            raise_errors=raise_errors,
        )


        # TODO - to be changed to entity resolver
        if identity.id == system_identity.id:
            data["user"] = {
                "id": system_identity.id,
                "email": "system@system.org",
            }  # TODO: Remove this after confirming system user email is passed
            data["user_id"] = system_identity.id
        else:
            user = current_datastore.get_user(identity.id)
            user_blob = {"id": str(user.id), "email": user.email}
            if user.username:
                user_blob["name"] = user.username
            data["user"] = user_blob
            data["user_id"] = user.id

        record = self.record_cls.create(
            {},
            **data,
        )

        # The user and session data is populated via component
        self.run_components("create", identity=identity, record=record)
        # Persist record (DB and index)
        uow.register(AuditRecordCommitOp(record, self.indexer))

        return self.result_item(
            self,
            identity,
            record,
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
