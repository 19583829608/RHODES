"""The ``list_pets`` MCP tool.

Strict 1:1 adapter for the Go backend endpoint::

    GET /api/v1/pets

The 14 accepted argument names are the backend query parameter names
(camelCase where the backend uses camelCase); no adapter-private business
arguments are added.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from mcp_types import CallToolResult, TextContent
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from ..errors import AppError, ErrorCode
from ..logging_config import ToolCallTimer, get_logger

if TYPE_CHECKING:
    from ..rest_client import PetHospitalClient

LOGGER = get_logger("tools.list_pets")

TOOL_NAME = "list_pets"

# Allowed values mirror the real Go backend:
# - species/status: internal/model ValidSpecies / ValidStatus
# - sortBy:         internal/api /api/v1/meta "sortFields"
# - order:          internal/store sortPets() asc/desc semantics
SPECIES_VALUES = ("犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他")
STATUS_VALUES = ("待就诊", "就诊中", "住院中", "已康复", "慢性病随访")
SORT_BY_VALUES = (
    "id",
    "name",
    "ownerName",
    "species",
    "doctor",
    "disease",
    "status",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
)
ORDER_VALUES = ("asc", "desc")

Species = Literal[
    "犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"
]
Status = Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"]
SortBy = Literal[
    "id",
    "name",
    "ownerName",
    "species",
    "doctor",
    "disease",
    "status",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
]
Order = Literal["asc", "desc"]

# Reusable constrained annotations shared by the input model and the tool
# function signature, so the advertised JSON Schema cannot drift. Strict
# numeric types reject numeric strings, booleans and fractional page numbers.
# Constraints live on each union arm so the generated JSON Schema advertises
# a standard ``minimum`` for both the number and integer leaf variants.
NonNegativeMoney = Union[
    Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)],
    Annotated[StrictInt, Field(ge=0)],
]
Page = Annotated[StrictInt, Field(ge=1)]
PageSize = Annotated[StrictInt, Field(ge=1, le=500)]

TOOL_DESCRIPTION = """\
查询宠物档案列表（适配 Go 后端 GET /api/v1/pets）。

用途：按关键词、宠物/主人信息、种类、主治医生、疾病、就诊状态和总花费区间
筛选宠物档案，支持排序与分页。

参数（全部可选，均与后端查询参数同名）：
- q: 跨字段关键词（全文模糊匹配）
- name: 宠物姓名（模糊）
- ownerName: 主人姓名（模糊）
- ownerPhone: 主人电话（模糊）
- species: 种类，取值 犬/猫/兔/鸟/仓鼠/爬宠/其他
- doctor: 主治医生姓名（模糊）
- disease: 疾病/诊断关键词（模糊）
- status: 就诊状态，取值 待就诊/就诊中/住院中/已康复/慢性病随访
- min/max: 在院总花费区间（非负，min 不得大于 max）
- sortBy: 排序字段 id/name/ownerName/species/doctor/disease/status/\
totalCost/visitCount/createdAt/updatedAt
- order: 排序方向 asc/desc
- page: 页码，从 1 开始
- pageSize: 每页条数，1-500

适用场景：Agent 需要检索、列举或分页浏览在院宠物档案及其总花费时使用。

返回值（成功）：对应后端响应信封 data 字段——items（宠物数组，含病历
records 与收费 charges，可能为 null）、total、page、pageSize、totalPages、
totalCost。失败时返回统一错误结构 {error:{code,message,details}}，
isError=true。\
"""


class ListPetsInput(BaseModel):
    """Strict input model for ``list_pets``."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = None
    name: str | None = None
    ownerName: str | None = None
    ownerPhone: str | None = None
    species: Species | None = None
    doctor: str | None = None
    disease: str | None = None
    status: Status | None = None
    min: NonNegativeMoney | None = None
    max: NonNegativeMoney | None = None
    sortBy: SortBy | None = None
    order: Order | None = None
    page: Page | None = None
    pageSize: PageSize | None = None

    @model_validator(mode="after")
    def _check_cost_range(self) -> "ListPetsInput":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min 不能大于 max")
        return self

    def to_query_params(self) -> dict[str, Any]:
        """Non-None values keyed by the exact backend query parameter names."""
        return {
            key: value
            for key, value in self.model_dump(by_alias=True, exclude_none=True).items()
        }


# ---------------------------------------------------------------------------
# Success output models (mirror the Go `data` payload / store.Result)
# ---------------------------------------------------------------------------


class MedicalRecordModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    visitDate: str | None = None
    doctor: str | None = None
    diagnosis: str | None = None
    symptoms: str | None = None
    treatment: str | None = None
    prescription: list[str] | None = None
    weightKg: float | None = None
    temperature: float | None = None
    followUp: str | None = None
    charge: float | None = None
    createdAt: str | None = None


class TreatmentModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    item: str | None = None
    category: str | None = None
    amount: float | None = None
    doctor: str | None = None
    date: str | None = None
    note: str | None = None


class PetModel(BaseModel):
    """A pet record. ``records``/``charges`` may be null in real Go JSON."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    name: str | None = None
    species: str | None = None
    breed: str | None = None
    gender: str | None = None
    ageMonths: int | None = None
    color: str | None = None
    chipNo: str | None = None
    ownerName: str | None = None
    ownerPhone: str | None = None
    ownerAddr: str | None = None
    doctor: str | None = None
    disease: str | None = None
    status: str | None = None
    allergy: str | None = None
    note: str | None = None
    records: list[MedicalRecordModel] | None = Field(default=None)
    charges: list[TreatmentModel] | None = Field(default=None)
    totalCost: float | None = None
    visitCount: int | None = None
    createdAt: str | None = None
    updatedAt: str | None = None

    @field_validator("records", "charges", mode="before")
    @classmethod
    def _null_to_list(cls, value: Any) -> Any:
        # Go serialises nil slices as JSON null; normalise to an empty list.
        return [] if value is None else value


class ListPetsSuccess(BaseModel):
    """Success output: the Go response envelope's ``data`` object."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    items: list[PetModel]
    total: int
    page: int
    pageSize: int
    totalPages: int
    totalCost: float


# ---------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------


def _text(payload: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


def success_result(data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=_text(data),
        structured_content=data,
        is_error=False,
    )


def error_result(error: AppError) -> CallToolResult:
    payload = error.to_envelope()
    return CallToolResult(
        content=_text(payload),
        structured_content=payload,
        is_error=True,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_list_pets(server: Any, client: PetHospitalClient) -> None:
    """Register the ``list_pets`` tool on an MCPServer instance.

    The parameter annotations intentionally mirror ``ListPetsInput``; the
    generated JSON Schema is the strict contract advertised to clients. The
    server middleware rejects invalid raw arguments before this function
    runs, so the body only handles validated values and upstream failures.
    """

    async def list_pets(
        q: str | None = None,
        name: str | None = None,
        ownerName: str | None = None,
        ownerPhone: str | None = None,
        species: Species | None = None,
        doctor: str | None = None,
        disease: str | None = None,
        status: Status | None = None,
        min: NonNegativeMoney | None = None,
        max: NonNegativeMoney | None = None,
        sortBy: SortBy | None = None,
        order: Order | None = None,
        page: Page | None = None,
        pageSize: PageSize | None = None,
    ) -> CallToolResult:
        raw_arguments = {
            "q": q,
            "name": name,
            "ownerName": ownerName,
            "ownerPhone": ownerPhone,
            "species": species,
            "doctor": doctor,
            "disease": disease,
            "status": status,
            "min": min,
            "max": max,
            "sortBy": sortBy,
            "order": order,
            "page": page,
            "pageSize": pageSize,
        }
        timer = ToolCallTimer(LOGGER, TOOL_NAME, raw_arguments)
        status_name = ErrorCode.INTERNAL_ERROR
        try:
            validated = ListPetsInput.model_validate(raw_arguments)
            data = await client.list_pets(validated.to_query_params())
            status_name = "success"
            return success_result(data)
        except AppError as error:
            status_name = error.code
            return error_result(error)
        except Exception as error:  # noqa: BLE001 - last-resort containment
            # Log only the exception type server-side; never leak internals.
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
        list_pets,
        name=TOOL_NAME,
        title="查询宠物档案列表",
        description=TOOL_DESCRIPTION,
    )
