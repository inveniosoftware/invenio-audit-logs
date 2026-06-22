# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

"""Change existing audit log ids to UUIDv7, based on each row's ``created`` time."""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f0e1d2c3b4a5"
down_revision = "c9a2f1d4e6b8"
branch_labels = ()
depends_on = None

# Build a new id for every row in one UPDATE. A UUIDv7 starts with a 48-bit
# millisecond timestamp, then the digit 7, then random bits. We take the timestamp
# from each row's ``created`` (stored as UTC), so the new ids sort in time order.
# ``gen_random_uuid()`` gives the random bits and comes built into PostgreSQL.
REWRITE_IDS_TO_UUID7 = """
UPDATE audit_logs_metadata
SET id = (
    lpad(to_hex((extract(epoch FROM created) * 1000)::bigint), 12, '0')
    || '7'
    || substr(replace(gen_random_uuid()::text, '-', ''), 1, 3)
    || to_hex(8 + floor(random() * 4)::int)
    || substr(replace(gen_random_uuid()::text, '-', ''), 1, 15)
)::uuid
"""


def upgrade():
    """Give every existing row a UUIDv7 id based on its ``created`` time.

    This is what lets an operator partition the table by time on the primary key.
    Changing the id is safe: audit log ids are never foreign keys, and retention
    deletes rows by ``created``, not by id, so nothing else changes. After this,
    rebuild the search copy from PostgreSQL with ``AuditLogService.reindex`` so
    OpenSearch uses the new ids.
    """
    op.execute(REWRITE_IDS_TO_UUID7)


def downgrade():
    """Do nothing: the change cannot be undone, and nothing points at these ids.

    The old ids are gone after the rewrite, and no other table references an audit
    log id, so there is nothing to put back.
    """
