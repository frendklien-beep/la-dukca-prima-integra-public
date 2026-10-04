"""add Sprint 5 remediation regulatory relationship metadata

Revision ID: 005r1
Revises: 005
"""

import sqlalchemy as sa

from alembic import op

revision = "005r1"
down_revision = "005"
branch_labels = None
depends_on = None

_COLUMNS = (
    sa.Column("document_type", sa.String(64), nullable=True),
    sa.Column("amends_json", sa.Text(), nullable=True),
    sa.Column("amended_by_json", sa.Text(), nullable=True),
    sa.Column("revokes_json", sa.Text(), nullable=True),
    sa.Column("revoked_by_json", sa.Text(), nullable=True),
    sa.Column("topics_json", sa.Text(), nullable=True),
)


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        for column in _COLUMNS:
            batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        for column in reversed(_COLUMNS):
            batch.drop_column(column.name)
