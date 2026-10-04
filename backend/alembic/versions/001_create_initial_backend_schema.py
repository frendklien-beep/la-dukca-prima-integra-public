"""create initial backend schema"""

import sqlalchemy as sa

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None
utc = sa.DateTime()


def upgrade():
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("failed_login_window_started_at", utc),
        sa.Column("locked_until", utc),
        sa.Column("last_login_at", utc),
        sa.Column("password_changed_at", utc, nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("updated_at", utc, nullable=False),
        sa.UniqueConstraint("username", name="uq_admins_username"),
        sa.CheckConstraint(
            "failed_login_count >= 0", name="ck_admins_failed_login_count_nonnegative"
        ),
        sa.CheckConstraint("role IN ('administrator')", name="ck_admins_role"),
    )
    op.create_index("ix_admins_locked_until", "admins", ["locked_until"])
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "admin_id", sa.Integer(), sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("remember_me", sa.Boolean(), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("last_seen_at", utc, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.Column("idle_expires_at", utc, nullable=False),
        sa.Column("revoked_at", utc),
        sa.Column("revoke_reason", sa.String(100)),
        sa.Column("created_user_agent_hash", sa.String(64)),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_admin_sessions_absolute_expiry"),
        sa.CheckConstraint("idle_expires_at > created_at", name="ck_admin_sessions_idle_expiry"),
    )
    for name, cols in [
        ("ix_admin_sessions_admin_id", ["admin_id"]),
        ("ix_admin_sessions_token_hash", ["token_hash"]),
        ("ix_admin_sessions_last_seen_at", ["last_seen_at"]),
        ("ix_admin_sessions_expires_at", ["expires_at"]),
        ("ix_admin_sessions_idle_expires_at", ["idle_expires_at"]),
        ("ix_admin_sessions_revoked_at", ["revoked_at"]),
        ("ix_admin_sessions_admin_active", ["admin_id", "revoked_at", "expires_at"]),
    ]:
        op.create_index(name, "admin_sessions", cols)
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("processing_status", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("extracted_char_count", sa.Integer()),
        sa.Column("processing_error_code", sa.String(100)),
        sa.Column("processing_error_message", sa.String(500)),
        sa.Column(
            "uploaded_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admins.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("processed_at", utc),
        sa.Column("activated_at", utc),
        sa.Column("archived_at", utc),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("updated_at", utc, nullable=False),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint("sha256_checksum", name="uq_documents_sha256_checksum"),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_documents_file_size_nonnegative"),
        sa.CheckConstraint(
            "processing_status IN ('pending','processing','ready','failed','requires_ocr')",
            name="ck_documents_processing_status",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0", name="ck_documents_page_count_nonnegative"
        ),
    )
    op.create_index(
        "ix_documents_retrieval", "documents", ["processing_status", "is_active", "archived_at"]
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("section_title", sa.String(255)),
        sa.Column("token_count", sa.Integer()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_chunk_index"
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_chunk_index_nonnegative"),
        sa.CheckConstraint(
            "page_start IS NULL OR page_start >= 1", name="ck_document_chunks_page_start_positive"
        ),
        sa.CheckConstraint(
            "page_end IS NULL OR page_end >= 1", name="ck_document_chunks_page_end_positive"
        ),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False),
        sa.Column("is_frontend_visible", sa.Boolean(), nullable=False),
        sa.Column("is_editable", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_by_admin_id", sa.Integer(), sa.ForeignKey("admins.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("updated_at", utc, nullable=False),
        sa.UniqueConstraint("key", name="uq_app_settings_key"),
        sa.CheckConstraint(
            "value_type IN ('string','integer','boolean','json')", name="ck_app_settings_value_type"
        ),
    )
    op.create_table(
        "public_chat_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.Column("last_activity_at", utc, nullable=False),
        sa.Column("expires_at", utc, nullable=False),
        sa.Column("closed_at", utc),
        sa.CheckConstraint(
            "status IN ('active','closed','expired')", name="ck_public_chat_sessions_status"
        ),
        sa.CheckConstraint(
            "message_count >= 0", name="ck_public_chat_sessions_message_count_nonnegative"
        ),
    )
    op.create_table(
        "public_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("public_chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("response_status", sa.String(40)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", utc, nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_public_chat_messages_role"),
    )
    op.create_index("ix_public_chat_messages_session_id", "public_chat_messages", ["session_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_admin_id", sa.Integer(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("entity_type", sa.String(100)),
        sa.Column("entity_id", sa.String(100)),
        sa.Column("request_id", sa.String(100)),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", utc, nullable=False),
        sa.CheckConstraint(
            "outcome IN ('success','failure','blocked')", name="ck_audit_events_outcome"
        ),
    )
    op.create_index("ix_audit_events_actor_admin_id", "audit_events", ["actor_admin_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_table(
        "message_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("public_chat_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("document_chunks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title_snapshot", sa.String(255), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("section_snapshot", sa.String(255)),
        sa.Column("relevance_score", sa.Float()),
        sa.Column("created_at", utc, nullable=False),
    )
    for c in ("message_id", "document_id", "chunk_id"):
        op.create_index(f"ix_message_sources_{c}", "message_sources", [c])


def downgrade():
    for table in [
        "message_sources",
        "audit_events",
        "public_chat_messages",
        "public_chat_sessions",
        "app_settings",
        "document_chunks",
        "documents",
        "admin_sessions",
        "admins",
    ]:
        op.drop_table(table)
