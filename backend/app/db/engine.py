from sqlalchemy import Engine, create_engine, event

from app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if engine.dialect.name == "sqlite":
        _register_sqlite_events(engine, settings)
    return engine


def _register_sqlite_events(engine: Engine, settings: Settings) -> None:
    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={settings.database_busy_timeout_ms}")
            if (
                settings.sqlite_wal_enabled
                and settings.database_url != "sqlite+pysqlite:///:memory:"
            ):
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("SQLite foreign key enforcement tidak aktif.")
        finally:
            cursor.close()
