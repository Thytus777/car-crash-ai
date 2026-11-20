"""Structured JSON logging with the current request ID on every line."""

import datetime as dt
import json
import logging
from contextvars import ContextVar

from app.core.config import settings
from app.core.tracing import current_trace_ids

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else was passed via `extra=`.
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON line: ts, level, severity, logger, message, request_id, extras."""

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, object] = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z",
            "level": record.levelname,
            # Cloud Logging reads the level from `severity`; Python's level
            # names are all valid LogSeverity values.
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            line["request_id"] = request_id
        line.update(
            {
                k: v
                for k, v in vars(record).items()
                if k not in _STANDARD and k != "request_id"
            }
        )
        ids = current_trace_ids()
        if ids:
            line["trace_id"], line["span_id"] = ids
        if record.exc_info:
            line["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging() -> None:
    """Route root logging through the JSON formatter (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    logging.captureWarnings(True)  # Python warnings become JSON lines too
    # Uvicorn's own access log would duplicate app.access without the request ID.
    logging.getLogger("uvicorn.access").disabled = True
