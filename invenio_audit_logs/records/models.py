# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 CERN.
#
# Invenio-Audit-Logs is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Base model classes for Audit Logs in Invenio."""

from invenio_db import db
from invenio_records.models import RecordMetadataBase
from sqlalchemy.types import String
from sqlalchemy_utils.types import UUIDType

try:
    from uuid import uuid7
except ImportError:
    from uuid_utils.compat import uuid7


class AuditLog(db.Model, RecordMetadataBase):
    """Model class for Audit Log."""

    __tablename__ = "audit_logs_metadata"

    encoder = None

    id = db.Column(
        UUIDType,
        primary_key=True,
        default=uuid7,
    )

    action = db.Column(String(255), nullable=False)

    resource_type = db.Column(String(255), nullable=False)

    user_id = db.Column(String(255), nullable=False)
