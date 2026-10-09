"""SDK 2.x stateless connection flow for protocol version 2026-07-28.

Verifies:
- tools are discoverable and callable with no legacy ``initialize`` handshake;
- the server never requires or returns ``Mcp-Session-Id``;
- discovery uses the modern ``server/discover`` exchange;
- ``/health`` works;
- repeated independent POSTs behave statelessly.
"""

from __future__ import annotations

from typing import Any

import httpx

from conftest import Harness, call_list_pets, mcp_request  # noqa: E402


def go_list() -> dict[str, Any]:
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "items": [],
            "total": 0,
            "page": 1,
            "pageSize": 20,
            "totalPages": 0,
            "totalCost": 0,
        },
        "time": "2026-09-16T10:00:00+08:00",
    }


async def test_server_discover_without_initialize(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=go_list())

    harness: Harness = await start_harness(handler)

    # The very first request is server/discover - no initialize precedes it.
    discover = await mcp_request(harness.http, harness.base_url, "server/discover")
    assert discover.status_code == 200
    assert discover.headers.get("mcp-session-id") is None
    result = discover.json()["result"]
    assert "capabilities" in result
    assert "tools" in result["capabilities"]
    supported = result.get("supportedVersions") or result.get("supported_versions")
    assert "2026-07-28" in supported


async def test_tools_discoverable_and_callable_statelessly(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=go_list())

    harness = await start_harness(handler)

    # Two completely independent single-exchange POSTs; neither sends nor
    # receives Mcp-Session-Id, and no initialize/initialized messages exist.
    for request_id in (1, 2):
        response = await call_list_pets(
            harness, {"species": "猫", "page": 1, "pageSize": 5}, request_id=request_id
        )
        assert response.status_code == 200
        assert response.headers.get("mcp-session-id") is None
        body = response.json()
        assert body["id"] == request_id
        assert body["result"]["isError"] is False
        assert body["result"]["structuredContent"]["items"] == []

    # Both requests were served independently by the stateless endpoint.
    assert len(harness.requests) == 2
    assert all(request.url.path == "/api/v1/pets" for request in harness.requests)


async def test_call_without_session_id_header_succeeds(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=go_list())

    harness = await start_harness(handler)

    # Explicitly prove no session header is needed on a fresh request.
    raw = await harness.http.post(
        f"{harness.base_url}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "list_pets",
                "arguments": {},
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        },
        headers={
            "mcp-protocol-version": "2026-07-28",
            "mcp-method": "tools/call",
            "mcp-name": "list_pets",
            "Accept": "application/json",
            # Deliberately no Mcp-Session-Id.
        },
    )
    assert raw.status_code == 200
    assert raw.headers.get("mcp-session-id") is None
    assert raw.json()["result"]["isError"] is False


async def test_health_endpoint(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=go_list())

    harness = await start_harness(handler)
    response = await harness.http.get(f"{harness.base_url}/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "pet-hospital-mcp"
    assert "timestamp" in payload
    assert payload["backend_base_url"] == "http://upstream.test"


async def test_mcp_endpoint_is_post_only(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=go_list())

    harness = await start_harness(handler)
    # The modern entry point rejects non-POST with 405; without the version
    # header a bare GET would instead enter the legacy SSE stream and hang.
    response = await harness.http.get(
        f"{harness.base_url}/mcp",
        headers={"mcp-protocol-version": "2026-07-28"},
    )
    assert response.status_code == 405
    assert response.headers.get("allow") == "POST"
