# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-License-Identifier: MIT

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

    index = IndexField("auditlog", search_alias="auditlog")
    """Read alias spanning the monthly ``auditlog-YYYY-MM`` indices.

    Writes route to a per-month index derived from ``created`` (see
    ``AuditLogService.record_to_index``); this alias is what search and refresh
    use to reach every month at once.
    """

    id = ModelField("id", dump_type=UUID)

    created = ModelField("created", dump_type=datetime, dump_key="@timestamp")

    action = systemfields.ActionField("action", dump_type=str)

    user_id = ModelField("user_id", dump=False, dump_type=str)

    user = DictField("user")

    resource_type = ModelField("resource_type", dump=False, dump_type=str)

    resource = DictField("resource")

    #: Metadata system field. Overrides clear_none from base class to allow empty values.
    metadata = DictField(clear_none=False, create_if_missing=True)
