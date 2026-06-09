"""Logging terstruktur (JSON satu-baris) memakai stdlib `logging`."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from .context import get_request_id, get_trace_id

_EXTRA_FIELDS = (
    "request_id",
    "trace_id",
    "error_code",
    "path",
    "method",
    "status_code",
    "duration_ms",
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            rid = get_request_id()
            if rid is not None:
                record.request_id = rid
        if not hasattr(record, "trace_id"):
            tid = get_trace_id()
            if tid is not None:
                record.trace_id = tid
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True
