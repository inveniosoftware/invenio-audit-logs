# SPDX-FileCopyrightText: 2025 CERN.
# SPDX-License-Identifier: MIT

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


class RetentionRun(db.Model):
    """One deleted (action, month) recorded by a retention run.

    The audit log table cannot vouch for its own deletions, since it is the data
    being removed and is itself subject to retention. This table lives apart from
    ``audit_logs_metadata`` so it survives those deletions and stays queryable as
    proof that the policy ran. It holds counts and status only, never event
    content.
    """

    __tablename__ = "audit_logs_retention_runs"

    id = db.Column(db.Integer, primary_key=True)

    run_at = db.Column(db.DateTime, nullable=False)
    """When the retention run executed (naive UTC)."""

    action = db.Column(String(255), nullable=False)

    retention_days = db.Column(db.Integer, nullable=False)
    """The applied retention period, in days."""

    month = db.Column(db.Date, nullable=False)
    """First day of the deleted month."""

    rows_deleted = db.Column(db.Integer, nullable=False)

    status = db.Column(String(32), nullable=False)
