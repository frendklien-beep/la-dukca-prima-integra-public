import json

from sqlalchemy.orm import Session

from app.db.utc import utc_now
from app.models.audit_event import AuditEvent

ALLOWED_METADATA = {
    "admin_id",
    "session_id",
    "reason_code",
    "remember_me",
    "revoked_session_count",
    "cleaned_count",
    "password_hash_rehashed",
    "changed_keys",
    "created_keys",
    "document_id",
    "category_code",
    "file_size_bytes",
    "processing_status",
    "page_count",
    "chunk_count",
    "pipeline_version",
    "error_code",
    "vector_dimension",
    "previous_status",
}


class AuditRepository:
    def append_event(
        self,
        session: Session,
        *,
        event_type: str,
        outcome: str,
        request_id: str | None,
        actor_admin_id: int | None = None,
        metadata: dict | None = None,
    ) -> AuditEvent:
        safe_metadata = {
            key: value for key, value in (metadata or {}).items() if key in ALLOWED_METADATA
        }
        event = AuditEvent(
            actor_admin_id=actor_admin_id,
            event_type=event_type,
            outcome=outcome,
            entity_type=None,
            entity_id=None,
            request_id=request_id,
            metadata_json=json.dumps(
                safe_metadata,
                separators=(",", ":"),
                sort_keys=True,
            ),
            created_at=utc_now(),
        )
        session.add(event)
        session.flush()
        return event
