"""End-to-end tests for the list_pets MCP tool over stateless HTTP.

Covers:
1. happy path + full filter/sort/paging parameter forwarding;
2. strict input validation;
3. upstream 4xx / 5xx;
4. upstream timeout / connection failure;
5. malformed upstream JSON / data model;
6. tool registration, name and JSON Schema.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from conftest import Harness, call_list_pets, mcp_request  # noqa: E402

from pet_hospital_mcp.tools.list_pets import (  # noqa: E402
    ORDER_VALUES,
    SORT_BY_VALUES,
    SPECIES_VALUES,
    STATUS_VALUES,
    ListPetsInput,
    TOOL_NAME,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def go_envelope(data: Any, message: str = "ok", code: int = 200) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data, "time": "2026-09-16T10:00:00+08:00"}


def pet_payload() -> dict[str, Any]:
    return {
        "id": "PET-000001",
        "name": "旺财",
        "species": "犬",
        "breed": "金毛",
        "gender": "公",
        "ageMonths": 36,
        "color": "金黄",
        "chipNo": "900000000001",
        "ownerName": "张三",
        "ownerPhone": "13800001111",
        "ownerAddr": "北京市朝阳区",
        "doctor": "李医生",
        "disease": "急性肠胃炎",
        "status": "就诊中",
        "allergy": "无",
        "note": "",
        # Real Go JSON may carry null slices.
        "records": None,
        "charges": None,
        "totalCost": 1380.0,
        "visitCount": 0,
        "createdAt": "2026-01-01T09:00:00+08:00",
        "updatedAt": "2026-01-02T09:00:00+08:00",
    }


def list_data() -> dict[str, Any]:
    return {
        "items": [pet_payload()],
        "total": 1,
        "page": 1,
        "pageSize": 10,
        "totalPages": 1,
        "totalCost": 1380.0,
    }


def structured(result_body: dict[str, Any]) -> dict[str, Any]:
    return result_body["result"]["structuredContent"]


def error_payload(result_body: dict[str, Any]) -> dict[str, Any]:
    return structured(result_body)["error"]


# ---------------------------------------------------------------------------
# 1. Happy path + forwarding
# ---------------------------------------------------------------------------


async def test_list_pets_success_forwards_all_params(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/pets"
        data = list_data()
        # Echo paging so the response model can be checked against the request.
        data["page"] = int(request.url.params.get("page", "1"))
        data["pageSize"] = int(request.url.params.get("pageSize", "20"))
        return httpx.Response(200, json=go_envelope(data))

    harness: Harness = await start_harness(handler)
    arguments = {
        "q": "肠胃炎",
        "name": "旺",
        "ownerName": "张",
        "ownerPhone": "138",
        "species": "犬",
        "doctor": "李",
        "disease": "肠胃炎",
        "status": "就诊中",
        "min": 100.5,
        "max": 5000,
        "sortBy": "totalCost",
        "order": "desc",
        "page": 2,
        "pageSize": 20,
    }

    response = await call_list_pets(harness, arguments)

    assert response.status_code == 200
    # Stateless: the server never issues a session id.
    assert response.headers.get("mcp-session-id") is None

    body = response.json()
    assert "error" not in body
    result = body["result"]
    assert result.get("isError") is False

    data = structured(body)
    assert set(data.keys()) == {"items", "total", "page", "pageSize", "totalPages", "totalCost"}
    assert data["page"] == 2
    assert data["pageSize"] == 20
    item = data["items"][0]
    assert item["id"] == "PET-000001"
    # null records/charges normalised to empty arrays.
    assert item["records"] == []
    assert item["charges"] == []

    # Every filter/sort/paging parameter reached the Go backend verbatim.
    assert len(harness.requests) == 1
    sent = harness.requests[0].url.params
    assert sent["q"] == "肠胃炎"
    assert sent["name"] == "旺"
    assert sent["ownerName"] == "张"
    assert sent["ownerPhone"] == "138"
    assert sent["species"] == "犬"
    assert sent["doctor"] == "李"
    assert sent["disease"] == "肠胃炎"
    assert sent["status"] == "就诊中"
    assert sent["min"] == "100.5"
    assert sent["max"] == "5000"
    assert sent["sortBy"] == "totalCost"
    assert sent["order"] == "desc"
    assert sent["page"] == "2"
    assert sent["pageSize"] == "20"

    # Unstructured content mirrors the structured payload.
    text_block = result["content"][0]
    assert text_block["type"] == "text"
    assert json.loads(text_block["text"]) == data


async def test_list_pets_empty_arguments_omits_query_string(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=go_envelope(list_data()))

    harness = await start_harness(handler)
    response = await call_list_pets(harness, {})

    assert response.status_code == 200
    assert harness.requests[0].url.query == b""


# ---------------------------------------------------------------------------
# 2. Input validation
# ---------------------------------------------------------------------------


INVALID_CASES = [
    ({"page": 0}, "page"),
    ({"pageSize": 0}, "pageSize"),
    ({"pageSize": 501}, "pageSize"),
    ({"min": -1}, "min"),
    ({"max": -0.01}, "max"),
    # Cross-field rule surfaces on the model rather than on one field.
    ({"min": 100, "max": 50}, None),
    ({"species": "狗"}, "species"),
    ({"status": "已出院"}, "status"),
    ({"sortBy": "password"}, "sortBy"),
    ({"order": "up"}, "order"),
    ({"page": "2"}, "page"),
    ({"pageSize": 1.5}, "pageSize"),
    ({"unknown_field": 1}, "unknown_field"),
]


@pytest.mark.parametrize("arguments,field", INVALID_CASES)
async def test_invalid_arguments_rejected(
    start_harness: Any, arguments: dict[str, Any], field: str | None
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("upstream must not be called for invalid input")

    harness = await start_harness(handler)
    response = await call_list_pets(harness, arguments)

    assert response.status_code == 200
    assert harness.requests == []
    result = response.json()["result"]
    assert result["isError"] is True
    error = error_payload(response.json())
    assert error["code"] == "VALIDATION_ERROR"
    if field is not None:
        assert field in error["details"]["fields"]
    else:
        # Model-level cross-field rule (min <= max).
        assert "min" in error["message"] and "max" in error["message"]
    # No library internals leak.
    serialized = str(error).lower()
    assert "pydantic" not in serialized
    assert "traceback" not in serialized


async def test_nan_and_infinity_rejected(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("upstream must not be called")

    harness = await start_harness(handler)

    # httpx refuses NaN/Infinity in its JSON encoder, so send the raw tokens.
    for token in ("NaN", "Infinity", "-Infinity"):
        raw_body = (
            '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{'
            '"name":"list_pets","arguments":{"min":' + token + '},'
            '"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",'
            '"io.modelcontextprotocol/clientCapabilities":{}}}}'
        )
        response = await harness.http.post(
            f"{harness.base_url}/mcp",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "mcp-protocol-version": "2026-07-28",
                "mcp-method": "tools/call",
                "mcp-name": "list_pets",
                "Accept": "application/json",
            },
        )
        assert response.json()["result"]["isError"] is True
        assert error_payload(response.json())["code"] == "VALIDATION_ERROR"
    assert harness.requests == []


async def test_arguments_wrong_type_rejected(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("upstream must not be called")

    harness = await start_harness(handler)
    # Send a raw body whose arguments are not an object.
    raw_response = await harness.http.post(
        f"{harness.base_url}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "list_pets",
                "arguments": "not-an-object",
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
        },
    )
    assert raw_response.status_code == 200
    body = raw_response.json()
    assert body["result"]["isError"] is True
    assert error_payload(body)["code"] == "VALIDATION_ERROR"
    assert harness.requests == []


# ---------------------------------------------------------------------------
# 3. Upstream 4xx / 5xx
# ---------------------------------------------------------------------------


async def test_upstream_4xx_no_retry(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 400, "message": "参数错误", "data": None})

    harness = await start_harness(handler, max_retries=2)
    response = await call_list_pets(harness, {"page": 1})

    body = response.json()
    assert body["result"]["isError"] is True
    error = error_payload(body)
    assert error["code"] == "BACKEND_API_ERROR"
    assert error["details"]["http_status"] == 400
    assert error["details"]["backend_message"] == "参数错误"
    assert len(harness.requests) == 1  # 4xx is not retried


async def test_upstream_5xx_retried_then_error(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    harness = await start_harness(handler, max_retries=1)
    response = await call_list_pets(harness, {})

    body = response.json()
    assert body["result"]["isError"] is True
    assert error_payload(body)["code"] == "BACKEND_API_ERROR"
    assert error_payload(body)["details"]["http_status"] == 503
    assert len(harness.requests) == 2  # initial attempt + one retry


# ---------------------------------------------------------------------------
# 4. Timeout / connection errors
# ---------------------------------------------------------------------------


async def test_upstream_timeout(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout containing internal detail")

    harness = await start_harness(handler, max_retries=0)
    response = await call_list_pets(harness, {})

    body = response.json()
    assert body["result"]["isError"] is True
    error = error_payload(body)
    assert error["code"] == "BACKEND_TIMEOUT"
    serialized = str(error)
    assert "simulated timeout" not in serialized
    assert "httpx" not in serialized.lower()


async def test_upstream_connection_refused(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 10061] connection refused, internals here")

    harness = await start_harness(handler, max_retries=0)
    response = await call_list_pets(harness, {})

    body = response.json()
    assert body["result"]["isError"] is True
    error = error_payload(body)
    assert error["code"] == "BACKEND_UNAVAILABLE"
    serialized = str(error)
    assert "10061" not in serialized
    assert "httpx" not in serialized.lower()


# ---------------------------------------------------------------------------
# 5. Malformed upstream responses
# ---------------------------------------------------------------------------


async def test_upstream_invalid_json(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="oops this is not json", headers={"content-type": "text/plain"})

    harness = await start_harness(handler)
    response = await call_list_pets(harness, {})

    body = response.json()
    assert body["result"]["isError"] is True
    assert error_payload(body)["code"] == "BACKEND_INVALID_RESPONSE"


async def test_upstream_wrong_data_model(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        # Envelope present, but data does not match store.Result.
        return httpx.Response(
            200,
            json=go_envelope({"items": "not-a-list", "total": 1}),
        )

    harness = await start_harness(handler)
    response = await call_list_pets(harness, {})

    body = response.json()
    assert body["result"]["isError"] is True
    assert error_payload(body)["code"] == "BACKEND_INVALID_RESPONSE"


async def test_upstream_missing_data_field(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "message": "ok"})

    harness = await start_harness(handler)
    response = await call_list_pets(harness, {})

    assert error_payload(response.json())["code"] == "BACKEND_INVALID_RESPONSE"


# ---------------------------------------------------------------------------
# 6. Tool registration, name and JSON Schema
# ---------------------------------------------------------------------------


async def test_tool_registration_and_json_schema(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=go_envelope(list_data()))

    harness = await start_harness(handler)
    response = await mcp_request(harness.http, harness.base_url, "tools/list")

    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    tool = next(tool for tool in tools if tool["name"] == TOOL_NAME)

    # snake_case tool name
    assert tool["name"] == "list_pets"
    assert tool["title"] == "查询宠物档案列表"
    assert "GET /api/v1/pets" in tool["description"]
    assert "pageSize" in tool["description"]

    schema = tool["inputSchema"]
    advertised_props = set(schema["properties"])
    expected_props = set(ListPetsInput.model_json_schema()["properties"])
    assert advertised_props == expected_props
    assert advertised_props == {
        "q",
        "name",
        "ownerName",
        "ownerPhone",
        "species",
        "doctor",
        "disease",
        "status",
        "min",
        "max",
        "sortBy",
        "order",
        "page",
        "pageSize",
    }

    def flatten(node: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect leaf variants, descending through nested anyOf unions."""
        if "anyOf" in node:
            leaves: list[dict[str, Any]] = []
            for variant in node["anyOf"]:
                leaves.extend(flatten(variant))
            return leaves
        return [node]

    def variants_of(prop: str) -> list[dict[str, Any]]:
        return flatten(schema["properties"][prop])

    def enum_of(prop: str) -> list[str]:
        return next(
            variant["enum"] for variant in variants_of(prop) if "enum" in variant
        )

    assert enum_of("species") == list(SPECIES_VALUES)
    assert enum_of("status") == list(STATUS_VALUES)
    assert enum_of("sortBy") == list(SORT_BY_VALUES)
    assert enum_of("order") == list(ORDER_VALUES)

    def constraints_of(prop: str, json_type: str) -> dict[str, Any]:
        return next(
            variant
            for variant in variants_of(prop)
            if variant.get("type") == json_type and "minimum" in variant
        )

    assert constraints_of("min", "number")["minimum"] == 0
    assert constraints_of("max", "number")["minimum"] == 0
    assert constraints_of("page", "integer")["minimum"] == 1
    page_size = constraints_of("pageSize", "integer")
    assert page_size["minimum"] == 1
    assert page_size["maximum"] == 500

    # Every parameter is optional and explicitly allows null. Forbidding
    # unknown parameters itself is covered behaviorally in the validation
    # cases above (extra=forbid).
    assert all(
        any(variant.get("type") == "null" for variant in variants_of(prop))
        for prop in advertised_props
    )


async def test_unknown_tool_name(start_harness: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("upstream must not be called")

    harness = await start_harness(handler)
    response = await mcp_request(
        harness.http,
        harness.base_url,
        "tools/call",
        {"name": "does_not_exist", "arguments": {}},
        name="does_not_exist",
    )
    body = response.json()
    # The SDK surfaces an unknown tool as a failed tool execution result;
    # either way it must never reach the upstream.
    assert "result" in body
    assert body["result"]["isError"] is True
    assert harness.requests == []
