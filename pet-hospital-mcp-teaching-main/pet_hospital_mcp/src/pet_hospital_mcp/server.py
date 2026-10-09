"""MCP server assembly.

Uses the SDK 2.x ``MCPServer`` (not the legacy ``FastMCP``) and exposes it as
a stateless Streamable HTTP application for protocol version 2026-07-28:

- no ``initialize`` handshake (the modern single-exchange path);
- no ``Mcp-Session-Id`` issued or required;
- one self-contained JSON-RPC POST per HTTP request;
- ``server/discover`` is served by the SDK's built-in handler.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from mcp.server import MCPServer
from mcp.server.context import ServerMiddleware, ServerRequestContext
from mcp_types import CallToolResult
from pydantic import ValidationError
from starlette.responses import JSONResponse

from .config import Settings
from .errors import AppError, ErrorCode, validation_error_from_pydantic
from .logging_config import configure_logging, get_logger
from .rest_client import PetHospitalClient
from .tools.create_pet import (
    CreatePetInput,
    TOOL_NAME as CREATE_PET_TOOL_NAME,
    register_create_pet,
)
from .tools.list_pets import (
    TOOL_NAME as LIST_PETS_TOOL_NAME,
    ListPetsInput,
    error_result,
    register_list_pets,
)

LOGGER = get_logger("server")

SERVER_NAME = "pet-hospital-mcp"
SERVER_TITLE = "宠物医院 MCP 适配服务"
SERVER_VERSION = "1.0.0"
SERVER_INSTRUCTIONS = (
    "宠物医院 MCP 服务：将 Go 宠物医院 REST API 的能力暴露给 AI Agent。"
    "提供 list_pets（查询宠物档案列表，支持过滤/排序/分页）和 "
    "create_pet（新增宠物档案）两个工具。"
)


def strict_input_validation_middleware() -> ServerMiddleware[Any]:
    """Validate raw ``tools/call`` arguments before the SDK parses them.

    The middleware tier runs before SDK-side parameter validation, which lets
    us answer every invalid tool input with the unified structured error
    envelope (``isError=true``) instead of leaking Pydantic/SDK error text.
    """

    input_models: dict[str, type[Any]] = {
        LIST_PETS_TOOL_NAME: ListPetsInput,
        CREATE_PET_TOOL_NAME: CreatePetInput,
    }

    async def middleware(
        ctx: ServerRequestContext[Any, Any], call_next: Any
    ) -> CallToolResult | Any:
        if ctx.method == "tools/call" and isinstance(ctx.params, Mapping):
            params = ctx.params
            tool_name = params.get("name")
            model = input_models.get(tool_name) if isinstance(tool_name, str) else None
            if model is not None:
                arguments = params.get("arguments")
                if arguments is None:
                    arguments = {}
                if not isinstance(arguments, Mapping):
                    return error_result(
                        AppError(
                            ErrorCode.VALIDATION_ERROR,
                            "输入参数校验失败：arguments 必须是对象",
                            {"fields": {"arguments": "参数类型必须是对象"}},
                        )
                    )
                try:
                    model.model_validate(dict(arguments))
                except ValidationError as exc:
                    return error_result(validation_error_from_pydantic(exc))
        return await call_next(ctx)

    return middleware


def build_server(client: PetHospitalClient, *, log_level: str = "INFO") -> MCPServer:
    """Create the MCPServer with tools, validation middleware and /health."""
    configure_logging(log_level)

    server = MCPServer(
        name=SERVER_NAME,
        title=SERVER_TITLE,
        version=SERVER_VERSION,
        instructions=SERVER_INSTRUCTIONS,
        log_level=log_level,
        middleware=[strict_input_validation_middleware()],
    )

    register_list_pets(server, client)
    register_create_pet(server, client)

    @server.custom_route("/health", methods=["GET"])
    async def health_check(request: Any) -> JSONResponse:
        return JSONResponse(
            {
                "status": "healthy",
                "service": SERVER_NAME,
                "version": SERVER_VERSION,
                "backend_base_url": client.base_url,
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )

    return server


def build_http_app(server: MCPServer, settings: Settings) -> Any:
    """Return the stateless Streamable HTTP Starlette application.

    ``stateless_http=True`` and ``json_response=True`` give the pure
    request/response model required for teaching: no session store, no
    session expiry, no SSE resumption.
    """
    return server.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        stateless_http=True,
        json_response=True,
        host=settings.mcp_host,
    )
