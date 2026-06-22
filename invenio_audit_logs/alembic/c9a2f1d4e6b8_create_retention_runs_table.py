# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Create audit log retention runs table."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "c9a2f1d4e6b8"
down_revision = "42fa8d3bbc0c"
branch_labels = ()
depends_on = None


def upgrade():
    """Upgrade database."""
    op.create_table(
        "audit_logs_retention_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "run_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("rows_deleted", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs_retention_runs")),
    )


def downgrade():
    """Downgrade database."""
    op.drop_table("audit_logs_retention_runs")
