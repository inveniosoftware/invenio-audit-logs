# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit Logs Service API."""

from flask import request
from invenio_accounts.proxies import current_datastore
from invenio_records_resources.services.records import RecordService
from invenio_records_resources.services.uow import unit_of_work

from .uow import AuditLogOp


class AuditLogService(RecordService):
    """Audit log service layer."""

    def _get_user_context(self, identity):
        """Return user context."""
        return {
            "user_account": current_datastore.get_user(identity.id),
            "ip_address": request.headers.get("REMOTE_ADDR") or request.remote_addr,
            "session": request.cookies.get("SESSION") or request.cookies.get("session"),
        }

    @unit_of_work()
    def create(self, identity, data, raise_errors=True, uow=None):
        """Create a record.

        :param identity: Identity of user creating the record.
        :param dict data: Input data according to the data schema.
        :param bool raise_errors: raise schema ValidationError or not.
        """
        self.require_permission(identity, "create", user_identity=identity)

        # Validate data, action, resource_type and create record with id
        data, errors = self.schema.load(
            data,
            context={
                "identity": identity,
                "metadata": self._get_user_context(identity),
            },  # The user data is populated via context
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
