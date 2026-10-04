import logging
import time

from app.core.request_context import get_request_id


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class UTCFormatter(logging.Formatter):
    converter = time.gmtime


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    owned_handlers = [handler for handler in root.handlers if getattr(handler, "la_dukca", False)]
    if owned_handlers:
        for handler in owned_handlers:
            handler.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.la_dukca = True  # type: ignore[attr-defined]
    handler.setLevel(level)
    handler.addFilter(RequestIDFilter())
    handler.setFormatter(
        UTCFormatter(
            fmt="%(asctime)sZ %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
