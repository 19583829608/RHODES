"""HTTP client for the upstream Go Pet Hospital REST API.

All backend access goes through this module: bounded timeout, a small number
of retries (network errors / timeouts / HTTP 5xx only), and translation of
every failure mode into the unified :class:`AppError` contract. HTTPX
objects, raw exception strings and stack traces never cross the MCP boundary.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from .errors import AppError, ErrorCode
from .tools.list_pets import ListPetsSuccess, PetModel

PETS_PATH = "/api/v1/pets"


class PetHospitalClient:
    """Thin async client over the Go REST API.

    Args:
        base_url: Upstream origin, e.g. ``http://127.0.0.1:8080``.
        timeout: Per-attempt timeout in seconds.
        max_retries: Retries after the first attempt (0 disables retries).
        retry_backoff: Base seconds for exponential backoff between retries.
        transport: Optional custom httpx transport (used by tests with
            ``httpx.MockTransport``).
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        max_retries: int = 2,
        retry_backoff: float = 0.05,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max(0, max_retries)
        self.retry_backoff = retry_backoff
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "PetHospitalClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def list_pets(self, params: dict[str, Any]) -> dict[str, Any]:
        """Call ``GET /api/v1/pets`` and return the validated ``data`` payload."""
        response = await self._request_with_retry(
            "GET", PETS_PATH, params=params, upstream=PETS_PATH
        )
        return self._parse_success(response, PETS_PATH, ListPetsSuccess)

    async def create_pet(self, body: dict[str, Any]) -> dict[str, Any]:
        """Call ``POST /api/v1/pets`` and return the created pet ``data``."""
        response = await self._request_with_retry(
            "POST", PETS_PATH, json=body, upstream=PETS_PATH
        )
        return self._parse_success(response, PETS_PATH, PetModel)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        upstream: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Send one HTTP request with bounded retries.

        Retries only on network errors, timeouts and HTTP 5xx. Client errors
        (4xx) are deterministic and raise immediately.
        """
        attempts = self.max_retries + 1
        last_error: AppError | None = None

        for attempt in range(attempts):
            if attempt > 0:
                await asyncio.sleep(self.retry_backoff * (2 ** (attempt - 1)))
            try:
                response = await self._client.request(
                    method, url, params=params, json=json
                )
            except httpx.TimeoutException:
                last_error = AppError(
                    ErrorCode.BACKEND_TIMEOUT,
                    "调用宠物医院后端服务超时，请稍后重试",
                    {"upstream": upstream, "timeout_seconds": self._timeout},
                )
                continue
            except httpx.TransportError:
                last_error = AppError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    "无法连接到宠物医院后端服务，请确认 Go REST API 已启动",
                    {"upstream": upstream},
                )
                continue

            if response.status_code >= 500:
                last_error = AppError(
                    ErrorCode.BACKEND_API_ERROR,
                    f"宠物医院后端服务暂时不可用（HTTP {response.status_code}）",
                    {"upstream": upstream, "http_status": response.status_code},
                )
                continue

            if response.status_code >= 400:
                raise AppError(
                    ErrorCode.BACKEND_API_ERROR,
                    f"宠物医院后端 API 返回错误（HTTP {response.status_code}）",
                    {
                        "upstream": upstream,
                        "http_status": response.status_code,
                        "backend_message": _safe_backend_message(response),
                    },
                )

            return response

        assert last_error is not None
        raise last_error

    def _parse_success(
        self, response: httpx.Response, upstream: str, model: type[BaseModel]
    ) -> dict[str, Any]:
        """Validate the Go envelope ``data`` field against ``model``."""
        try:
            payload = response.json()
        except ValueError:
            raise AppError(
                ErrorCode.BACKEND_INVALID_RESPONSE,
                "宠物医院后端返回了无法解析的 JSON",
                {"upstream": upstream},
            ) from None

        if not isinstance(payload, dict) or "data" not in payload:
            raise AppError(
                ErrorCode.BACKEND_INVALID_RESPONSE,
                "宠物医院后端响应缺少统一信封的 data 字段",
                {"upstream": upstream},
            )

        try:
            result = model.model_validate(payload["data"])
        except ValidationError:
            raise AppError(
                ErrorCode.BACKEND_INVALID_RESPONSE,
                f"宠物医院后端返回的数据结构不符合 {model.__name__} 预期模型",
                {"upstream": upstream},
            ) from None

        return result.model_dump(mode="json", by_alias=True)


def _safe_backend_message(response: httpx.Response) -> str | None:
    """Best-effort extraction of the Go envelope's readable ``message``."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str):
            return message[:300]
    return None
