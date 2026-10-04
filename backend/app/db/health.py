from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import DatabaseUnavailableError


def check_database(engine: Engine) -> str:
    try:
        with engine.connect() as connection:
            if connection.execute(text("SELECT 1")).scalar_one() != 1:
                raise RuntimeError("database probe gagal")
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        raise DatabaseUnavailableError() from exc
    return "ready"
