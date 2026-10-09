"""The ``create_pet`` MCP tool.

Strict 1:1 adapter for the Go backend endpoint::

    POST /api/v1/pets

The accepted argument names are the backend JSON body field names
(camelCase where the backend uses camelCase); no adapter-private business
arguments are added. Server-generated fields (``id``, ``records``,
``charges``, ``totalCost``, ``visitCount``, ``createdAt``, ``updatedAt``)
are rejected on input.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Any

from mcp_types import CallToolResult
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)

from ..errors import AppError, ErrorCode
from ..logging_config import ToolCallTimer, get_logger
from .list_pets import error_result, success_result

if TYPE_CHECKING:
    from ..rest_client import PetHospitalClient

LOGGER = get_logger("tools.create_pet")

TOOL_NAME = "create_pet"

# Mirror the Go backend's ValidSpecies / ValidStatus.
SPECIES_VALUES = ("犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他")
STATUS_VALUES = ("待就诊", "就诊中", "住院中", "已康复", "慢性病随访")
GENDER_VALUES = ("公", "母")

# Phone validation mirrors model.ValidatePhone: 7-15 digits with the
# separator characters -, +, space, ( and ).
_PHONE_DIGIT_RE = re.compile(r"[0-9]")
_PHONE_ALLOWED_RE = re.compile(r"^[0-9+\- ()]+$")

NonNegativeInt = Annotated[StrictInt, Field(ge=0)]

TOOL_DESCRIPTION = """\
新增宠物档案（适配 Go 后端 POST /api/v1/pets）。

用途：为宠物医院录入一条新的宠物档案，包含宠物基本信息、主人信息、
主治医生与主要诊断。后端会自动生成档案编号、就诊次数与总花费等只读字段。

必填参数（均与后端 JSON 字段同名）：
- name: 宠物姓名
- ownerName: 主人姓名
- ownerPhone: 主人电话（7-15 位数字，可含 + - 空格 括号）
- doctor: 主治医生姓名
- disease: 疾病 / 主要诊断

可选参数：
- species: 种类，取值 犬/猫/兔/鸟/仓鼠/爬宠/其他（默认 其他）
- breed: 品种
- gender: 性别，取值 公/母
- ageMonths: 月龄（非负整数）
- color: 毛色
- chipNo: 芯片号
- ownerAddr: 主人住址
- status: 就诊状态，取值 待就诊/就诊中/住院中/已康复/慢性病随访（默认 待就诊）
- allergy: 过敏史
- note: 备注

返回值（成功）：后端创建后的完整宠物档案（data 字段），包含自动生成的
id、totalCost、visitCount、createdAt 等字段。失败时返回统一错误结构
{error:{code,message,details}}，isError=true。\
"""


def _validate_phone(value: str) -> str:
    """Validate a phone number the same way the Go backend does."""
    if not _PHONE_ALLOWED_RE.match(value):
        raise ValueError("电话含非法字符，仅允许数字与 + - 空格 括号")
    digits = len(_PHONE_DIGIT_RE.findall(value))
    if digits < 7 or digits > 15:
        raise ValueError("电话位数不合法，需 7-15 位数字")
    return value


class CreatePetInput(BaseModel):
    """Strict input model for ``create_pet``.

    Server-generated and read-only fields (id, records, charges, totalCost,
    visitCount, createdAt, updatedAt) are rejected via ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="forbid")

    # --- required fields ---
    name: str
    ownerName: str
    ownerPhone: str
    doctor: str
    disease: str

    # --- optional fields with backend defaults ---
    species: str | None = None
    status: str | None = None

    # --- purely optional fields ---
    breed: str | None = None
    gender: str | None = None
    ageMonths: NonNegativeInt | None = None
    color: str | None = None
    chipNo: str | None = None
    ownerAddr: str | None = None
    allergy: str | None = None
    note: str | None = None

    @field_validator("name", "ownerName", "doctor", "disease")
    @classmethod
    def _non_empty_required(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("不能为空")
        return value

    @field_validator("ownerPhone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return _validate_phone(value)

    @field_validator("species")
    @classmethod
    def _species(cls, value: str | None) -> str | None:
        if value is not None and value not in SPECIES_VALUES:
            raise ValueError(f"必须是 {', '.join(SPECIES_VALUES)} 之一")
        return value

    @field_validator("status")
    @classmethod
    def _status(cls, value: str | None) -> str | None:
        if value is not None and value not in STATUS_VALUES:
            raise ValueError(f"必须是 {', '.join(STATUS_VALUES)} 之一")
        return value

    @field_validator("gender")
    @classmethod
    def _gender(cls, value: str | None) -> str | None:
        if value is not None and value not in GENDER_VALUES:
            raise ValueError(f"必须是 {', '.join(GENDER_VALUES)} 之一")
        return value

    def to_body(self) -> dict[str, Any]:
        """Non-None values keyed by the exact backend JSON field names."""
        return {
            key: value
            for key, value in self.model_dump(by_alias=True, exclude_none=True).items()
        }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_create_pet(server: Any, client: PetHospitalClient) -> None:
    """Register the ``create_pet`` tool on an MCPServer instance."""

    async def create_pet(
        name: str,
        ownerName: str,
        ownerPhone: str,
        doctor: str,
        disease: str,
        species: str | None = None,
        breed: str | None = None,
        gender: str | None = None,
        ageMonths: NonNegativeInt | None = None,
        color: str | None = None,
        chipNo: str | None = None,
        ownerAddr: str | None = None,
        status: str | None = None,
        allergy: str | None = None,
        note: str | None = None,
    ) -> CallToolResult:
        raw_arguments = {
            "name": name,
            "ownerName": ownerName,
            "ownerPhone": ownerPhone,
            "doctor": doctor,
            "disease": disease,
            "species": species,
            "breed": breed,
            "gender": gender,
            "ageMonths": ageMonths,
            "color": color,
            "chipNo": chipNo,
            "ownerAddr": ownerAddr,
            "status": status,
            "allergy": allergy,
            "note": note,
        }
        timer = ToolCallTimer(LOGGER, TOOL_NAME, raw_arguments)
        status_name = ErrorCode.INTERNAL_ERROR
        try:
            validated = CreatePetInput.model_validate(raw_arguments)
            data = await client.create_pet(validated.to_body())
            status_name = "success"
            return success_result(data)
        except AppError as error:
            status_name = error.code
            return error_result(error)
        except Exception as error:  # noqa: BLE001 - last-resort containment
            LOGGER.error(
                "unexpected tool failure: %s",
                type(error).__name__,
                extra={
                    "tool_name": TOOL_NAME,
                    "params": raw_arguments,
                    "status": ErrorCode.INTERNAL_ERROR,
                },
            )
            return error_result(
                AppError(ErrorCode.INTERNAL_ERROR, "MCP 服务内部错误，请稍后重试")
            )
        finally:
            timer.finish(status_name)

    server.add_tool(
        create_pet,
        name=TOOL_NAME,
        title="新增宠物档案",
        description=TOOL_DESCRIPTION,
    )
