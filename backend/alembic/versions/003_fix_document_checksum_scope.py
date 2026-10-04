"""replace global document checksum uniqueness with non-archived partial uniqueness

Revision ID: 003
Revises: 002
"""

import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents", recreate="always") as batch:
        batch.drop_constraint("uq_documents_sha256_checksum", type_="unique")

    op.create_index(
        "uq_documents_sha256_non_archived",
        "documents",
        ["sha256_checksum"],
        unique=True,
        sqlite_where=sa.text("archived_at IS NULL"),
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_sha256_non_archived", table_name="documents")
    with op.batch_alter_table("documents", recreate="always") as batch:
        batch.create_unique_constraint("uq_documents_sha256_checksum", ["sha256_checksum"])
