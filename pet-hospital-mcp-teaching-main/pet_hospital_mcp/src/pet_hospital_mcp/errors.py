"""Unified structured error contract shared by every MCP tool.

Wire shape::

    {"error": {"code": "ERROR_CODE", "message": "...", "details": {}}}

Tool-originated failures are returned inside the MCP ``CallToolResult`` with
``isError=true`` (the mechanism mcp 2.0.0 / protocol 2026-07-28 still
prescribes, as verified in the installed SDK's ``CallToolResult`` model),
never as raw HTTPX/Pydantic/SDK strings or stack traces.
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    BACKEND_API_ERROR = "BACKEND_API_ERROR"
    BACKEND_INVALID_RESPONSE = "BACKEND_INVALID_RESPONSE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorBody(BaseModel):
    """The ``error`` object of the unified envelope."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    """Top-level error envelope returned to MCP clients."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class AppError(Exception):
    """An error that must be serialized to the unified error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})

    def to_envelope(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


# Human-readable Chinese descriptions for the pydantic error types we surface.
# Anything not listed falls back to a generic message, so validator internals
# (type ids, stack frames, library names) never reach MCP clients directly.
_CONSTRAINT_MESSAGES = {
    "greater_than_equal": "不能小于允许的最小值",
    "less_than_equal": "不能大于允许的最大值",
    "greater_than": "必须大于允许的最小值",
    "less_than": "必须小于允许的最大值",
    "finite_number": "不允许使用 NaN 或 Infinity",
    "string_type": "参数类型必须是字符串",
    "int_type": "参数类型必须是整数",
    "number_type": "参数类型必须是数字",
    "literal_error": "取值不在允许范围内",
    "enum": "取值不在允许范围内",
    "extra_forbidden": "不允许传入未知参数",
    "bool_type": "参数类型必须是布尔值",
}


# Union-arm type mismatches are noise when another arm fails on a value
# constraint: for ``min=-0.01`` the meaningful error is "below minimum", not
# "must be an integer". Constraint failures therefore win over type failures.
_TYPE_PRIORITY = {
    "greater_than_equal": 2,
    "less_than_equal": 2,
    "greater_than": 2,
    "less_than": 2,
    "finite_number": 2,
    "value_error": 2,
}


def validation_error_from_pydantic(exc: ValidationError) -> AppError:
    """Convert a Pydantic ValidationError into a VALIDATION_ERROR AppError.

    Produces stable, readable field-level messages in ``details.fields`` while
    intentionally omitting raw pydantic error strings. The input model is
    flat, so only the first component of a loc is the public parameter name;
    union-arm suffixes such as ``constrained-float`` are stripped.
    """
    # root field -> (priority, message), first occurrence keeps ordering.
    collected: dict[str, tuple[int, str]] = {}
    model_messages: list[str] = []
    for err in exc.errors():
        loc = tuple(part for part in err.get("loc", ()) if part != "")
        type_ = err.get("type", "")
        message = _CONSTRAINT_MESSAGES.get(type_)
        if message is None:
            if type_ == "value_error":
                # Cross-field model validators (min <= max etc.).
                message = str(err.get("ctx", {}).get("error", "")) or "参数校验失败"
            else:
                message = "参数不合法"
        priority = _TYPE_PRIORITY.get(type_, 1)
        if not loc:
            if message not in model_messages:
                model_messages.append(message)
            continue
        root = str(loc[0])
        previous = collected.get(root)
        if previous is None or priority > previous[0]:
            collected[root] = (priority, message)

    fields = {field: text for field, (_, text) in collected.items()}
    field_messages = [f"{field}: {text}" for field, (_, text) in collected.items()]
    human_parts = model_messages + field_messages
    human = "；".join(human_parts) if human_parts else "工具输入参数校验失败"
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        f"输入参数校验失败：{human}",
        {"fields": fields},
    )
