from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import document_error


@dataclass(frozen=True, slots=True)
class StorageKeys:
    temp_path: Path
    final_path: Path
    storage_key: str


class DocumentStorage:
    def prepare(self, settings: Settings, now: datetime) -> StorageKeys:
        temp_dir = settings.uploads_dir / ".tmp"
        final_dir = settings.uploads_dir / f"{now.year:04d}" / f"{now.month:02d}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)
        identifier = uuid4().hex
        temp_path = temp_dir / f"{identifier}.upload"
        final_path = final_dir / f"{identifier}.pdf"
        storage_key = final_path.relative_to(settings.data_dir).as_posix()
        return StorageKeys(temp_path=temp_path, final_path=final_path, storage_key=storage_key)

    def finalize(self, temp_path: Path, final_path: Path) -> None:
        if final_path.exists():
            raise document_error(
                "DOCUMENT_STORAGE_UNAVAILABLE",
                "Penyimpanan dokumen tidak tersedia.",
                503,
                retryable=True,
            )
        temp_path.replace(final_path)

    @staticmethod
    def remove(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def resolve(settings: Settings, storage_key: str) -> Path:
        root = settings.data_dir.resolve()
        candidate = (settings.data_dir / storage_key).resolve()
        if root not in candidate.parents:
            raise document_error(
                "DOCUMENT_STORAGE_UNAVAILABLE",
                "Penyimpanan dokumen tidak tersedia.",
                503,
            )
        return candidate
