from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine


@dataclass(frozen=True)
class MigrationState:
    status: str
    current: str | None
    head: str | None


def get_alembic_config(project_dir: Path, database_url: str) -> Config:
    config = Config(str(project_dir / "alembic.ini"))
    config.set_main_option("script_location", str(project_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["database_url_override"] = database_url
    return config


def inspect_migration_state(engine: Engine, project_dir: Path) -> MigrationState:
    config = get_alembic_config(project_dir, str(engine.url))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) != 1:
        return MigrationState("multiple_heads", None, None)
    head = heads[0]
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    except Exception:
        return MigrationState("error", None, head)
    if current is None:
        return MigrationState("missing", None, head)
    if current == head:
        return MigrationState("ready", current, head)
    return MigrationState("behind", current, head)
