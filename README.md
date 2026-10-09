<div align="center">

# 🛡️ protect

**一个 MCP（Model Context Protocol）学习与教学项目集合**

把现有服务能力暴露给 AI Agent 的实践样本：Go REST API → Python MCP 适配器 → AnythingLLM RAG

<p>
  <img src="https://img.shields.io/badge/MCP-2026--07--28-blue?style=flat-square" alt="mcp" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="python" />
  <img src="https://img.shields.io/badge/Go-stdlib-00ADD8?style=flat-square&logo=go&logoColor=white" alt="go" />
  <img src="https://img.shields.io/badge/SDK-mcp%202.0.0-blue?style=flat-square" alt="sdk" />
  <img src="https://img.shields.io/badge/status-teaching-blueviolet?style=flat-square" alt="status" />
</p>

</div>

---

## 📦 仓库结构

| 路径 | 说明 |
|---|---|
| [`pet-hospital-mcp-teaching-main/`](./pet-hospital-mcp-teaching-main) | 宠物医院教学项目：Go 标准库实现的 REST API + Python MCP 适配器（`list_pets` / `create_pet` 工具） |
| [`anythingllm-mcp/`](./anythingllm-mcp) | AnythingLLM MCP Server：封装本机 AnythingLLM 工作区，提供 `ask_workspace` RAG 问答工具 |
| [`windows/`](./windows) | Windows 发行版说明（可执行文件 + 数据库见同目录 zip 或 Releases） |
| [`.mcp.json`](./.mcp.json) | 项目级 MCP 客户端配置 |
| [`prompt-step1.md`](./prompt-step1.md) | 阶段一开发任务说明 |

## ✨ 特性

- **MCP 2026-07-28 规范**：无状态 Streamable HTTP，不使用旧版 `FastMCP`
- **官方 Python SDK `mcp==2.0.0`** 的 `MCPServer`
- **Go 标准库** 实现的宠物医院 REST API + 自研嵌入式存储（追加写日志 + CRC32 + 自动压实）
- **零第三方 Go 依赖**，单文件可迁移
- 完整的输入校验、结构化错误、日志脱敏、`pytest` 测试

## 🚀 快速开始

### 1. 启动宠物医院 Go 后端

```bash
cd pet-hospital-mcp-teaching-main
go run .              # 默认 http://127.0.0.1:8080
```

或直接使用 `windows/` 下的发行版（双击 `pethospital.exe`，浏览器打开 <http://127.0.0.1:8080/>）。

### 2. 启动宠物医院 MCP 适配器

```bash
cd pet-hospital-mcp-teaching-main/pet_hospital_mcp
pip install -e .
python -m pet_hospital_mcp     # 默认 127.0.0.1，端口/上游地址见子项目 README
```

### 3. 启动 AnythingLLM MCP（可选）

```bash
cd anythingllm-mcp
pip install -r requirements.txt
cp .env.example .env           # 填入 ANYTHINGLLM_API_KEY
python server.py               # 默认 http://127.0.0.1:8765/mcp
```

## 🧪 测试

```bash
cd pet-hospital-mcp-teaching-main/pet_hospital_mcp
pytest -q
```

## 🛠️ 技术栈

- **Go** 标准库（REST API + 嵌入式存储）
- **Python 3.10+** · `mcp==2.0.0` · `httpx` · `pydantic` · `pytest`
- **AnythingLLM** Developer API（RAG）

## 🔗 关键端点

| 服务 | 默认地址 |
|---|---|
| 宠物医院 REST API + 网页 | `http://127.0.0.1:8080/` |
| 宠物医院 MCP | `http://127.0.0.1:<MCP_PORT>/mcp` |
| AnythingLLM MCP | `http://127.0.0.1:8765/mcp` |
| AnythingLLM 本体 | `http://localhost:3001` |

## 📄 许可

见 [`pet-hospital-mcp-teaching-main/LICENSE`](./pet-hospital-mcp-teaching-main/LICENSE)。

---

<div align="center">
<i>教学用途 · 欢迎 Star / Issue</i>
</div>
