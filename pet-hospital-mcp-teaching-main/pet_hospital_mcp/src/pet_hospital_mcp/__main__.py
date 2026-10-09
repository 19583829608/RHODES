"""Entry point: ``python -m pet_hospital_mcp``."""

from __future__ import annotations

import anyio

from .config import Settings
from .logging_config import configure_logging, get_logger
from .rest_client import PetHospitalClient
from .server import build_server


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logger = get_logger("main")

    client = PetHospitalClient(
        settings.backend_base_url,
        timeout=settings.backend_timeout_seconds,
        max_retries=settings.backend_max_retries,
        retry_backoff=settings.backend_retry_backoff_seconds,
    )

    server = build_server(client, log_level=settings.log_level)

    logger.info(
        "starting MCP server",
        extra={
            "tool_name": "server",
            "params": {"mcp_path": settings.mcp_path},
            "status": "starting",
        },
    )
    print(
        f"🐾 pet-hospital-mcp listening on http://{settings.mcp_host}:{settings.mcp_port}"
        f"{settings.mcp_path} (stateless, protocol 2026-07-28)"
    )
    print(f"   health:  http://{settings.mcp_host}:{settings.mcp_port}/health")
    print(f"   backend: {settings.backend_base_url} (Go REST API must run separately)")

    try:
        server.run(
            "streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            streamable_http_path=settings.mcp_path,
            stateless_http=True,
            json_response=True,
        )
    finally:
        anyio.run(client.aclose)


if __name__ == "__main__":
    main()
