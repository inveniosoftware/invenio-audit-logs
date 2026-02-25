# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
# Copyright (C) 2025 Graz University of Technology.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Audit Logs Service API."""

from datetime import datetime, timezone

from invenio_records_resources.services.base.links import LinksTemplate
from invenio_records_resources.services.records import RecordService
from invenio_records_resources.services.records.schema import ServiceSchemaWrapper
from invenio_records_resources.services.uow import unit_of_work
from opensearchpy.exceptions import NotFoundError

from ..proxies import current_audit_logs_actions_registry
from .uow import AuditRecordCommitOp


class AuditLogService(RecordService):
    """Audit log service layer."""

    def _wrap_schema(self, schema):
        """Wrap schema."""
        return ServiceSchemaWrapper(self, schema=schema)

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
            data["created"] = datetime.now(timezone.utc).isoformat()

        # Dynamically load schema for metadata received from .build() method
        action_obj = current_audit_logs_actions_registry.get(data["action"])
        marshmallow_schema = action_obj.marshmallow_schema()

        # Validate data, action, resource_type and create record with id
        schema = self._wrap_schema(schema=marshmallow_schema)
        data, errors = schema.load(
            data,
            context={
                "identity": identity,
            },
            raise_errors=raise_errors,
        )

        record = self.record_cls.create(
            {},
            **data,
        )

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
        self.require_permission(identity, "read")

        # Read the record
        log = self.record_cls.get_record(id_=id_)

        # Return the result
        return self.result_item(
            self,
            identity,
            log,
            links_tpl=self.links_item_tpl,
        )

    def search(
        self, identity, params=None, search_preference=None, expand=False, **kwargs
    ):
        """Search for records matching the querystring."""
        self.require_permission(identity, "search")
        try:
            return super().search(identity, params, search_preference, expand, **kwargs)
        except NotFoundError as e:
            # Initially, audit logs only has an index_template
            # Therefore it will raise a NotFoundError if at least one record is not indexed yet.
            # We return an empty list in this case to avoid breaking the search endpoint.
            return self.result_list(
                self,
                identity,
                [],
                params=params,
                links_tpl=LinksTemplate(
                    self.config.links_search, context={"args": params}
                ),
            )
        except Exception as e:
            raise e
