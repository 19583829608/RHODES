"""JSON logging with recursive sensitive-field redaction.

Every tool call is logged with at least:
``timestamp``, ``tool_name``, ``params``, ``status``, ``duration_ms``.

Keys carrying personal data (``ownerPhone``, ``ownerAddr``, ``chipNo`` and
their snake_case spellings) are masked recursively, at every nesting depth.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

REDACTED = "***REDACTED***"

# Lower-cased key names that must never appear verbatim in logs.
SENSITIVE_KEYS = frozenset(
    {
        "ownerphone",
        "owner_phone",
        "owneraddr",
        "owner_addr",
        "chipno",
        "chip_no",
    }
)

def redact(value: Any) -> Any:
    """Return a copy of ``value`` with sensitive fields masked.

    Recurses into dicts, lists, tuples and Pydantic-like mappings. Scalar
    values are returned untouched; redaction is key-based.
    """
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                masked[key] = REDACTED
            else:
                masked[key] = redact(item)
        return masked
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, set):
        return {redact(item) for item in value}
    return value


class JsonFormatter(logging.Formatter):
    """Serialize log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("tool_name", "params", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact(value) if key == "params" else value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure the package logger with one JSON stderr handler."""
    logger = logging.getLogger("pet_hospital_mcp")
    logger.setLevel(level.upper())
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False


def get_logger(name: str = "pet_hospital_mcp") -> logging.Logger:
    return logging.getLogger(name if name.startswith("pet_hospital_mcp") else f"pet_hospital_mcp.{name}")


class ToolCallTimer:
    """Measure and log a single tool call with redacted params."""

    def __init__(self, logger: logging.Logger, tool_name: str, params: Any) -> None:
        self._logger = logger
        self._tool_name = tool_name
        self._params = params
        self._start = time.perf_counter()

    def finish(self, status: str) -> float:
        duration_ms = round((time.perf_counter() - self._start) * 1000, 3)
        self._logger.info(
            "tool call finished",
            extra={
                "tool_name": self._tool_name,
                "params": self._params,
                "status": status,
                "duration_ms": duration_ms,
            },
        )
        return duration_ms
