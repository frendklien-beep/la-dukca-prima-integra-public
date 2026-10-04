import logging
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import MigrationRequiredError, StorageUnavailableError
from app.db.health import check_database
from app.db.migration_state import inspect_migration_state
from app.schemas.system import ReadinessComponents, ReadinessData

logger = logging.getLogger(__name__)


def _probe_directory(directory: Path):
    probe = directory / f".readiness-{uuid4()}.tmp"
    try:
        probe.write_bytes(b"1")
        probe.read_bytes()
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            logger.warning("storage_probe_cleanup_failed")


def check_storage(settings: Settings) -> str:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        for directory in (settings.uploads_dir, settings.processed_dir, settings.indexes_dir):
            directory.mkdir(parents=True, exist_ok=True)
            _probe_directory(directory)
    except OSError as exc:
        raise StorageUnavailableError() from exc
    return "ready"


def get_readiness(settings: Settings, engine) -> ReadinessData:
    storage = check_storage(settings)
    database = check_database(engine)
    migration = inspect_migration_state(engine, settings.project_dir)
    if migration.status != "ready":
        raise MigrationRequiredError()
    components = ReadinessComponents(
        database=database,
        storage=storage,
        migrations="ready",
        ai_configuration="configured" if settings.ai_configured else "unconfigured",
    )
    return ReadinessData(status="ready", components=components)
