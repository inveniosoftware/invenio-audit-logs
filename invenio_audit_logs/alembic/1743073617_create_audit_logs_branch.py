# SPDX-FileCopyrightText: 2016-2018 CERN.
# SPDX-License-Identifier: MIT

"""Create Audit logs branch."""

# revision identifiers, used by Alembic.
revision = "1743073617"
down_revision = None
branch_labels = ("invenio_audit_logs",)
depends_on = "dbdbc1b19cf2"


def upgrade():
    """Upgrade database."""
    pass


def downgrade():
    """Downgrade database."""
    pass
