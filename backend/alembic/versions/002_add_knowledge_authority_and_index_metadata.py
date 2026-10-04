"""add knowledge authority and index metadata"""

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None
columns = [
    sa.Column("authority_rank", sa.Integer()),
    sa.Column("document_number", sa.String(120)),
    sa.Column("document_year", sa.Integer()),
    sa.Column("issuer", sa.String(255)),
    sa.Column("jurisdiction", sa.String(64)),
    sa.Column("effective_date", sa.Date()),
    sa.Column("valid_until", sa.Date()),
    sa.Column("legal_status", sa.String(32)),
    sa.Column("indexed_at", sa.DateTime()),
    sa.Column("index_version", sa.String(64)),
    sa.Column("extraction_method", sa.String(64)),
    sa.Column("text_quality_score", sa.Float()),
]


def upgrade():
    with op.batch_alter_table("documents") as batch:
        for col in columns:
            batch.add_column(col)


def downgrade():
    with op.batch_alter_table("documents") as batch:
        for col in reversed(columns):
            batch.drop_column(col.name)
