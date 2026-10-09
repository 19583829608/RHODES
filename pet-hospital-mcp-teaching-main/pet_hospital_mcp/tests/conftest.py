"""Test fixtures.

The MCP app is served by a real uvicorn server bound to 127.0.0.1 on an
ephemeral port (so the tests exercise the actual stateless HTTP endpoint,
routing, lifespan and headers), while the Go upstream is replaced by an
``httpx.MockTransport`` — tests never touch a real Go service.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
import uvicorn

from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.rest_client import PetHospitalClient
from pet_hospital_mcp.server import build_http_app, build_server

PROTOCOL_VERSION = "2026-07-28"
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"

UpstreamHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@dataclass
class Harness:
    base_url: str
    http: httpx.AsyncClient
    client: PetHospitalClient
    requests: list[httpx.Request] = field(default_factory=list)


@pytest.fixture(name="start_harness")
async def start_harness_fixture() -> Callable[..., Awaitable[Harness]]:
    running: list[tuple[Any, Any, Harness]] = []

    async def start(
        handler: UpstreamHandler,
        *,
        max_retries: int = 0,
        timeout: float = 2.0,
        retry_backoff: float = 0.01,
    ) -> Harness:
        harness = Harness(
            base_url="",
            http=httpx.AsyncClient(timeout=10.0),
            client=None,  # type: ignore[arg-type]
        )

        async def recording(request: httpx.Request) -> httpx.Response:
            harness.requests.append(request)
            return await handler(request)

        harness.client = PetHospitalClient(
            "http://upstream.test",
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            transport=httpx.MockTransport(recording),
        )

        port = _free_port()
        mcp_server = build_server(harness.client, log_level="ERROR")
        settings = Settings(
            mcp_host="127.0.0.1",
            mcp_port=port,
            mcp_path="/mcp",
            backend_base_url="http://upstream.test",
        )
        app = build_http_app(mcp_server, settings)

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        task = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.01)

        harness.base_url = f"http://127.0.0.1:{port}"
        running.append((task, server, harness))
        return harness

    yield start

    for task, server, harness in reversed(running):
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        finally:
            await harness.http.aclose()
            await harness.client.aclose()


async def mcp_request(
    http: httpx.AsyncClient,
    base_url: str,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    request_id: int = 1,
    name: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Send one self-contained 2026-07-28 JSON-RPC POST."""
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {
            "_meta": {
                META_PROTOCOL_VERSION: PROTOCOL_VERSION,
                META_CLIENT_CAPABILITIES: {},
            },
            **(params or {}),
        },
    }
    headers = {
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
        "Accept": "application/json",
    }
    if name is not None:
        headers["mcp-name"] = name
    if extra_headers:
        headers.update(extra_headers)
    return await http.post(f"{base_url}/mcp", json=body, headers=headers)


async def call_list_pets(
    harness: Harness,
    arguments: dict[str, Any],
    **kwargs: Any,
) -> httpx.Response:
    return await mcp_request(
        harness.http,
        harness.base_url,
        "tools/call",
        {"name": "list_pets", "arguments": arguments},
        name="list_pets",
        **kwargs,
    )
