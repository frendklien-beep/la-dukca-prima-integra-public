from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

from app.core.config import Settings
from app.services.knowledge.errors import IndexWriteError
from app.services.knowledge.types import IndexMetadataRow, PreparedChunk, PreparedIndex


@dataclass(slots=True)
class IndexPromotion:
    store: KnowledgeIndexStore
    document_id: int
    final_dir: Path
    previous_manifest: bytes | None
    committed: bool = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        if self.committed:
            return
        shutil.rmtree(self.final_dir, ignore_errors=True)
        self.store._restore_manifest(self.previous_manifest)


class KnowledgeIndexStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.indexes_dir
        self.manifest_path = self.root / "manifest.json"

    def artifact_path(self, document_id: int, index_version: str) -> Path:
        return self.root / "documents" / str(document_id) / index_version / "embeddings.npy"

    def metadata_path(self, document_id: int, index_version: str) -> Path:
        return self.root / "documents" / str(document_id) / index_version / "metadata.json"

    def _read_manifest_bytes(self) -> bytes | None:
        try:
            return self.manifest_path.read_bytes()
        except FileNotFoundError:
            return None

    def _manifest(self) -> dict:
        raw = self._read_manifest_bytes()
        if raw is None:
            return {
                "index_schema_version": self.settings.index_schema_version,
                "embedding_model": self.settings.openai_embedding_model,
                "pipeline_version": self.settings.knowledge_pipeline_version,
                "updated_at": None,
                "documents": {},
            }
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IndexWriteError() from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("documents"), dict):
            raise IndexWriteError()
        return payload

    def _write_atomic(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise IndexWriteError() from exc

    def _restore_manifest(self, previous: bytes | None) -> None:
        if previous is None:
            self.manifest_path.unlink(missing_ok=True)
        else:
            self._write_atomic(self.manifest_path, previous)

    @staticmethod
    def _content_checksum(chunks: tuple[PreparedChunk, ...]) -> str:
        digest = hashlib.sha256()
        for chunk in chunks:
            digest.update(chunk.content_hash.encode("ascii"))
        return digest.hexdigest()

    def remove_document_version(self, document_id: int, index_version: str) -> None:
        version_dir = self.root / "documents" / str(document_id) / index_version
        shutil.rmtree(version_dir, ignore_errors=True)
        try:
            manifest = self._manifest()
            current = manifest.get("documents", {}).get(str(document_id))
            if current and current.get("index_version") == index_version:
                del manifest["documents"][str(document_id)]
                manifest["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                self._write_atomic(
                    self.manifest_path,
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode(
                        "utf-8"
                    ),
                )
        except IndexWriteError:
            return

    def promote(
        self,
        *,
        document_id: int,
        index_version: str,
        matrix: np.ndarray,
        chunks: tuple[PreparedChunk, ...],
        chunk_ids: tuple[int, ...],
    ) -> tuple[PreparedIndex, IndexPromotion]:
        if matrix.ndim != 2 or matrix.shape[0] != len(chunks) or len(chunk_ids) != len(chunks):
            raise IndexWriteError()
        if not np.all(np.isfinite(matrix)):
            raise IndexWriteError()
        final_dir = self.root / "documents" / str(document_id) / index_version
        if final_dir.exists():
            raise IndexWriteError()
        temporary = self.root / ".tmp" / f"document-{document_id}-{index_version}-{uuid4().hex}"
        previous_manifest = self._read_manifest_bytes()
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            embeddings_path = temporary / "embeddings.npy"
            with embeddings_path.open("wb") as target:
                np.save(target, matrix.astype(np.float32, copy=False), allow_pickle=False)
                target.flush()
                os.fsync(target.fileno())
            rows = [
                IndexMetadataRow(
                    row_index=row_index,
                    chunk_id=chunk_id,
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    content_hash=chunk.content_hash,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                )
                for row_index, (chunk_id, chunk) in enumerate(zip(chunk_ids, chunks, strict=True))
            ]
            metadata_payload = json.dumps(
                [
                    {
                        "row_index": row.row_index,
                        "chunk_id": row.chunk_id,
                        "document_id": row.document_id,
                        "chunk_index": row.chunk_index,
                        "content_hash": row.content_hash,
                        "page_start": row.page_start,
                        "page_end": row.page_end,
                        "section_title": row.section_title,
                    }
                    for row in rows
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self._write_atomic(temporary / "metadata.json", metadata_payload)

            loaded = np.load(embeddings_path, allow_pickle=False)
            if loaded.shape != matrix.shape or loaded.dtype != np.float32:
                raise IndexWriteError()
            metadata_check = json.loads((temporary / "metadata.json").read_text("utf-8"))
            if len(metadata_check) != len(chunks):
                raise IndexWriteError()

            final_dir.parent.mkdir(parents=True, exist_ok=True)
            temporary.replace(final_dir)
            manifest = self._manifest()
            manifest["index_schema_version"] = self.settings.index_schema_version
            manifest["embedding_model"] = self.settings.openai_embedding_model
            manifest["pipeline_version"] = self.settings.knowledge_pipeline_version
            manifest["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            manifest["documents"][str(document_id)] = {
                "index_version": index_version,
                "chunk_count": len(chunks),
                "vector_dimension": int(matrix.shape[1]),
                "content_checksum": self._content_checksum(chunks),
            }
            self._write_atomic(
                self.manifest_path,
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8"),
            )
            prepared = PreparedIndex(
                document_id=document_id,
                index_version=index_version,
                vector_dimension=int(matrix.shape[1]),
                chunk_count=len(chunks),
                content_checksum=self._content_checksum(chunks),
                version_dir=final_dir.as_posix(),
            )
            return prepared, IndexPromotion(
                store=self,
                document_id=document_id,
                final_dir=final_dir,
                previous_manifest=previous_manifest,
            )
        except Exception as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)
                self._restore_manifest(previous_manifest)
            if isinstance(exc, IndexWriteError):
                raise
            raise IndexWriteError() from exc
