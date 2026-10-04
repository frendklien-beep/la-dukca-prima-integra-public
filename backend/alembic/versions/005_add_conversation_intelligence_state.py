"""add conversation intelligence state

Revision ID: 005
Revises: 004
"""

import sqlalchemy as sa

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("public_chat_sessions") as batch:
        batch.add_column(sa.Column("greeting_sent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("public_chat_sessions") as batch:
        batch.drop_column("greeting_sent_at")
