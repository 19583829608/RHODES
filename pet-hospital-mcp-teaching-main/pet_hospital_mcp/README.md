# pet-hospital-mcp（阶段一）

将现有 **Go 宠物医院 REST API** 暴露给 AI Agent 的独立 Python MCP 服务。

- Python 3.11+（开发/测试环境：3.13）
- MCP SDK：**`mcp==2.0.0`**，使用 SDK 2.x 的 **`MCPServer`**（未使用、未导入 `mcp.server.fastmcp.FastMCP`）
- MCP 协议版本：**`2026-07-28`**
- 传输模型：**无状态 Streamable HTTP**（`stateless_http=True`、`json_response=True`）
  - 无旧版 `initialize` 握手；
  - 不签发、不要求 `Mcp-Session-Id`；
  - 无会话存储、会话过期、`max_sessions`，无有状态 SSE 恢复；
  - 每个 HTTP POST 是一次自包含的 JSON-RPC 交换。
- 教学场景：不实现认证、权限、CORS / Origin 校验；默认只监听 `127.0.0.1`。

阶段一**只提供一个工具 `list_pets`**，严格适配 Go 后端 `GET /api/v1/pets`。

## 目录结构

```text
pet_hospital_mcp/
├── pyproject.toml
├── README.md
├── src/
│   └── pet_hospital_mcp/
│       ├── __init__.py
│       ├── __main__.py        # python -m pet_hospital_mcp
│       ├── config.py          # 环境变量配置
│       ├── server.py          # MCPServer 装配、无状态 HTTP、/health、校验中间件
│       ├── rest_client.py     # Go REST API 客户端（超时/有限重试/错误映射）
│       ├── errors.py          # 统一错误信封与 6 个错误码
│       ├── logging_config.py  # JSON 日志 + 递归脱敏
│       └── tools/
│           ├── __init__.py
│           └── list_pets.py   # list_pets 工具：Pydantic 输入/输出模型与适配
└── tests/
    ├── conftest.py
    ├── test_logging_redaction.py
    ├── test_list_pets_http.py
    └── test_stateless_http.py
```

## 前置条件：先启动 Go REST API

MCP 服务本身不含业务数据，必须先在仓库根目录启动 Go 宠物医院服务（默认监听
`http://127.0.0.1:8080`），且只能通过 HTTP 调用它，不会修改 Go 服务。

## 安装与启动

```powershell
cd pet_hospital_mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

启动 MCP 服务：

```powershell
python -m pet_hospital_mcp
```

启动后可见：

```text
🐾 pet-hospital-mcp listening on http://127.0.0.1:8000/mcp (stateless, protocol 2026-07-28)
   health:  http://127.0.0.1:8000/health
   backend: http://127.0.0.1:8080 (Go REST API must run separately)
```

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | Go REST API 地址 |
| `MCP_HOST` | `127.0.0.1` | MCP 服务监听地址（默认仅本机） |
| `MCP_PORT` | `8000` | MCP 服务端口 |
| `MCP_PATH` | `/mcp` | MCP Streamable HTTP 端点路径 |
| `PET_HOSPITAL_TIMEOUT_SECONDS` | `5.0` | 上游单次请求超时（秒） |
| `PET_HOSPITAL_MAX_RETRIES` | `2` | 首次请求后的重试次数（仅网络错误/超时/5xx 重试，4xx 不重试） |
| `PET_HOSPITAL_RETRY_BACKOFF_SECONDS` | `0.05` | 指数退避基数（秒） |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别 |

## MCP 端点

- MCP Streamable HTTP 端点：`POST http://127.0.0.1:8000/mcp`
- 健康检查：`GET http://127.0.0.1:8000/health`

`2026-07-28` 请求头约定（SDK 现代无状态路径）：

- `mcp-protocol-version: 2026-07-28`
- `mcp-method`：与请求体 `method` 一致（如 `tools/call`）
- `mcp-name`：工具调用时等于参数中的工具名（如 `list_pets`）
- `Accept: application/json`
- 请求体 `params._meta` 必须包含
  `io.modelcontextprotocol/protocolVersion` 与
  `io.modelcontextprotocol/clientCapabilities`

### `/health` 示例

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

```json
{
  "status": "healthy",
  "service": "pet-hospital-mcp",
  "version": "1.0.0",
  "backend_base_url": "http://127.0.0.1:8080",
  "timestamp": "2026-09-16T03:45:48.601466Z"
}
```

## 工具：`list_pets`

查询宠物档案列表，1:1 转发到 `GET /api/v1/pets`，**不新增任何适配器私有参数**。

| 参数 | 类型 | 约束 / 允许值 |
| --- | --- | --- |
| `q` | string | 全文关键词 |
| `name` | string | 宠物名关键词 |
| `ownerName` | string | 主人姓名关键词 |
| `ownerPhone` | string | 主人电话 |
| `species` | string | `犬` `猫` `兔` `鸟` `仓鼠` `爬宠` `其他` |
| `doctor` | string | 主治医生关键词 |
| `disease` | string | 疾病关键词 |
| `status` | string | `待就诊` `就诊中` `住院中` `已康复` `慢性病随访` |
| `min` | number | 非负（费用下限），拒绝 NaN/Infinity |
| `max` | number | 非负（费用上限），拒绝 NaN/Infinity；要求 `min <= max` |
| `sortBy` | string | `id` `name` `ownerName` `species` `doctor` `disease` `status` `totalCost` `visitCount` `createdAt` `updatedAt` |
| `order` | string | `asc` / `desc` |
| `page` | integer | `>= 1` |
| `pageSize` | integer | `1 <= pageSize <= 500` |

严格校验：拒绝未知字段、NaN/Infinity、类型不正确的输入（如 `"page": "2"`、
`"pageSize": 1.5`、`"species": "狗"`）。

成功输出对应 Go 成功响应的 `data`：
`items`、`total`、`page`、`pageSize`、`totalPages`、`totalCost`；
并兼容 Go 中 `records`、`charges` 序列化为 `null` 或数组的真实表现（统一归一成数组）。

### 调用示例（2026-07-28 无状态请求）

```bash
curl -s http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'mcp-protocol-version: 2026-07-28' \
  -H 'mcp-method: tools/call' \
  -H 'mcp-name: list_pets' \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_pets",
      "arguments": {"species": "猫", "status": "就诊中", "page": 1, "pageSize": 5},
      "_meta": {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}
      }
    }
  }'
```

成功时返回 `result.isError=false`，`result.structuredContent` 即列表数据；
`result.content[0].text` 为同样内容的 JSON 文本。

发现服务（替代旧 `initialize` 的现代方式）：向同一端点发送
`method: "server/discover"`（同样携带上述 `_meta` 与头），响应
`supportedVersions` 包含 `2026-07-28`，且响应**没有** `Mcp-Session-Id` 头。

### 统一错误信封

任何无效输入或上游异常都以 `isError=true` 的 `CallToolResult` 返回
（mcp 2.0.0 仍采用该机制，已对照安装版 SDK 确认），内容为：

```json
{"error": {"code": "ERROR_CODE", "message": "可读错误信息", "details": {}}}
```

错误码：

- `VALIDATION_ERROR`：输入参数校验失败（`details.fields` 给出字段级原因）
- `BACKEND_TIMEOUT`：上游超时
- `BACKEND_UNAVAILABLE`：连接失败 / 网络不可达
- `BACKEND_API_ERROR`：上游返回非 2xx（`details.http_status`、`details.backend_message`）
- `BACKEND_INVALID_RESPONSE`：上游 JSON 非法或数据模型不符
- `INTERNAL_ERROR`：其他内部错误

错误信息不会泄露 HTTPX / Pydantic / SDK 原始字符串或 Python 堆栈。

## 日志

标准库 JSON logging，每次工具调用至少包含
`timestamp`、`tool_name`、`params`、`status`、`duration_ms`；
对 `ownerPhone`、`ownerAddr`、`chipNo` 及其 snake_case 写法
（`owner_phone`、`owner_addr`、`chip_no`）在任意嵌套层级递归脱敏为 `***REDACTED***`。

## 用 MCP Inspector / SDK 2.x 客户端验证

Inspector 连接地址填写 Streamable HTTP 端点：

```text
http://127.0.0.1:8000/mcp
```

连接后应能：无需 `initialize` 直接发现服务、在工具列表看到 `list_pets`、
查看其 14 个参数的 JSON Schema（枚举、`minimum`/`maximum`、可空），并直接调用。

SDK 2.x 客户端同样使用 2026-07-28 无状态 Streamable HTTP 传输接入，
无需管理会话 ID。

## 运行测试

测试使用 `pytest`、`pytest-asyncio` 与 `httpx.MockTransport`，
通过真实 uvicorn + 模拟上游完成端到端验证，**不会访问真实 Go 服务**。

```powershell
cd pet_hospital_mcp
pytest -q
```

预期结果：

```text
..................................................................
33 passed
```

覆盖：

1. 正常调用：路径与全部 14 个过滤/排序/分页参数转发；
2. 输入参数校验失败（含未知字段、NaN/Infinity、类型错误、枚举越界、`min > max` 等）；
3. 上游 4xx（不重试）/ 5xx（重试）；
4. 上游超时与连接异常；
5. 上游非法 JSON / 数据模型不符 / 缺少 `data`；
6. 工具注册、工具名与 JSON Schema；
7. SDK 2.x 无状态连接流程：无 `initialize`、无 `Mcp-Session-Id`、
   `server/discover`、工具经 HTTP 被发现与调用、`/health`、`GET /mcp` 返回 405。
