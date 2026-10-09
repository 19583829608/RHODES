# AnythingLLM MCP Server (MVP)

基于 **MCP 2026-07-28 规范**（无状态）的 Streamable HTTP MCP Server，封装本机 AnythingLLM 第一个工作区，提供 RAG 问答工具。

## 前置条件
- Python 3.10+
- 本机 AnythingLLM 运行于 `http://localhost:3001`，已创建至少 1 个工作区、上传文档、并配置了可用的 LLM 提供商
- 依赖已安装：`pip install -r requirements.txt`（mcp、httpx、python-dotenv）

## 配置
编辑 [.env](./.env)：
```
ANYTHINGLLM_BASE_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=你在 AnythingLLM 网页端「设置→工具→Developer API」创建的 Key
PORT=8765
```

## 启动 / 停止

### 前台运行（推荐，便于看日志）
在 `d:\protect\anythingllm-mcp` 目录执行：
```
python server.py
```
看到 `Uvicorn running on http://127.0.0.1:8765` 即启动成功。
**停止**：在该窗口按 `Ctrl+C`。

### 后台运行（PowerShell，独立进程）
```
Start-Process python -ArgumentList "server.py" -WorkingDirectory "d:\protect\anythingllm-mcp" -WindowStyle Hidden
```
**停止**（按占用端口的进程结束）：
```
Get-NetTCPConnection -LocalPort 8765 | Select-Object -ExpandProperty OwningProcess -Unique | Stop-Process -Force
```

## 项目级 MCP 配置
项目根 [`d:\protect\.mcp.json`](../.mcp.json) 已配置：
```json
{
  "mcpServers": {
    "anythingllm": {
      "type": "streamable-http",
      "url": "http://localhost:8765/mcp"
    }
  }
}
```
使用流程：
1. 先按上面方法启动 server
2. 在 Trae 中 reload 窗口或重启 IDE，让其识别 `.mcp.json`
3. IDE 会把 `ask_workspace` 工具暴露给模型调用

## 提供的工具
| 工具 | 入参 | 返回 |
|---|---|---|
| `ask_workspace` | `message: str`（问题） | RAG 答案 + 引用来源标题 |

自动取第一个工作区的 slug 并缓存，调用方无需指定工作区。

## 常见排错
| 现象 | 原因 / 解决 |
|---|---|
| 调用返回 `[AnythingLLM 错误 500] ... "402 status code"` | 该工作区 LLM 提供商 Key 无效/欠费。去 AnythingLLM 工作区设置配好 LLM（如本地 Ollama 或有效的 OpenAI Key） |
| 连接被拒 / `ConnectError` | server 没启动，或 8765 端口被占（改 `.env` 的 `PORT` 并同步改 `.mcp.json` 的 url） |
| `401 / 403` | AnythingLLM API Key 错，检查 `.env` |
| `工作区数量: 0` | AnythingLLM 里还没建工作区 |

## 文件结构
```
anythingllm-mcp/
├── server.py          # MCP Server（约 65 行，单工具）
├── requirements.txt   # mcp / httpx / python-dotenv
├── .env               # 你的本地配置（勿提交）
└── .env.example       # 配置模板
```
