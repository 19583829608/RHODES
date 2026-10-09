"""Runtime configuration loaded from environment variables.

The MCP service is an independent process; the Go REST API remains the only
business backend and is reached purely over HTTP.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_MCP_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 8000
DEFAULT_MCP_PATH = "/mcp"

# Upstream call budget: one initial attempt + this many retries.
DEFAULT_BACKEND_TIMEOUT_SECONDS = 5.0
DEFAULT_BACKEND_MAX_RETRIES = 2
# Small exponential backoff base (seconds) so teaching demos stay responsive.
DEFAULT_BACKEND_RETRY_BACKOFF_SECONDS = 0.05

DEFAULT_LOG_LEVEL = "INFO"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    """Process settings.

    Attributes:
        mcp_host: Interface the MCP HTTP server binds to (loopback by default).
        mcp_port: Port the MCP HTTP server listens on.
        mcp_path: Streamable HTTP endpoint path.
        backend_base_url: Base URL of the Go Pet Hospital REST API.
        backend_timeout_seconds: Per-attempt timeout for upstream HTTP calls.
        backend_max_retries: Retries after the first failed upstream attempt
            (only for network errors, timeouts and HTTP 5xx).
        backend_retry_backoff_seconds: Exponential backoff base.
        log_level: Standard library log level name.
    """

    mcp_host: str = DEFAULT_MCP_HOST
    mcp_port: int = DEFAULT_MCP_PORT
    mcp_path: str = DEFAULT_MCP_PATH
    backend_base_url: str = DEFAULT_BACKEND_BASE_URL
    backend_timeout_seconds: float = DEFAULT_BACKEND_TIMEOUT_SECONDS
    backend_max_retries: int = DEFAULT_BACKEND_MAX_RETRIES
    backend_retry_backoff_seconds: float = DEFAULT_BACKEND_RETRY_BACKOFF_SECONDS
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mcp_host=os.environ.get("MCP_HOST", DEFAULT_MCP_HOST),
            mcp_port=_env_int("MCP_PORT", DEFAULT_MCP_PORT),
            mcp_path=os.environ.get("MCP_PATH", DEFAULT_MCP_PATH),
            backend_base_url=os.environ.get(
                "PET_HOSPITAL_BASE_URL", DEFAULT_BACKEND_BASE_URL
            ).rstrip("/"),
            backend_timeout_seconds=_env_float(
                "PET_HOSPITAL_TIMEOUT_SECONDS", DEFAULT_BACKEND_TIMEOUT_SECONDS
            ),
            backend_max_retries=_env_int(
                "PET_HOSPITAL_MAX_RETRIES", DEFAULT_BACKEND_MAX_RETRIES
            ),
            backend_retry_backoff_seconds=_env_float(
                "PET_HOSPITAL_RETRY_BACKOFF_SECONDS",
                DEFAULT_BACKEND_RETRY_BACKOFF_SECONDS,
            ),
            log_level=os.environ.get("MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        )
