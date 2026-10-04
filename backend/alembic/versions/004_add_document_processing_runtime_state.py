"""add document processing runtime state

Revision ID: 004
Revises: 003
"""

import sqlalchemy as sa

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("processing_started_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_documents_processing_recovery",
        "documents",
        ["processing_status", "processing_started_at", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_processing_recovery", table_name="documents")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("processing_started_at")
