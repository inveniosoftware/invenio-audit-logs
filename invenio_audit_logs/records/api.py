# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""API classes for audit log event."""

from datetime import datetime
from uuid import UUID

from invenio_records.dumpers import SearchDumper
from invenio_records.systemfields import DictField, ModelField
from invenio_records_resources.records.api import Record
from invenio_records_resources.records.systemfields import IndexField

from . import models, systemfields


class AuditLog(Record):
    """API class to represent a structured audit-log event."""

    model_cls = models.AuditLog
    """The model class for the log."""

    dumper = SearchDumper(
        model_fields={
            "id": ("id", UUID),
            "created": ("@timestamp", datetime),
        },
    )
    """Search dumper with configured dump keys."""

    index = IndexField("auditlog-audit-log-v1.0.0", search_alias="auditlog")
    """The search engine index to use."""

    id = ModelField("id", dump_type=UUID)

    created = ModelField("created", dump_type=datetime, dump_key="@timestamp")

    action = systemfields.ActionField("action", dump_type=str)

    user_id = ModelField("user_id", dump=False, dump_type=str)

    user = DictField("user")

    resource_type = ModelField("resource_type", dump=False, dump_type=str)

    resource = DictField("resource")
