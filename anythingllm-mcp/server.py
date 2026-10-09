"""AnythingLLM MCP Server (MVP) - 单工具版，基于 MCP 2026-07-28 规范，Streamable HTTP 传输。"""
import os
import httpx
from dotenv import load_dotenv
from mcp.server import MCPServer

load_dotenv()
BASE_URL = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001")
API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
PORT = int(os.getenv("PORT", "8765"))

mcp = MCPServer("AnythingLLM")
_slug_cache: str | None = None


async def _first_workspace_slug() -> str:
    """获取第一个工作区的 slug，结果缓存。"""
    global _slug_cache
    if _slug_cache:
        return _slug_cache
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/api/v1/workspaces",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        r.raise_for_status()
        workspaces = r.json().get("workspaces", [])
        if not workspaces:
            raise RuntimeError("AnythingLLM 中没有工作区，请先创建并上传文档")
        _slug_cache = workspaces[0]["slug"]
        return _slug_cache


@mcp.tool()
async def ask_workspace(message: str) -> str:
    """向 AnythingLLM 第一个工作区提问，返回基于该工作区文档的 RAG 答案及引用来源。

    Args:
        message: 用户的问题。
    """
    slug = await _first_workspace_slug()
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{BASE_URL}/api/v1/workspace/{slug}/chat",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={"message": message, "mode": "chat"},
        )
    if r.status_code != 200:
        return f"[AnythingLLM 错误 {r.status_code}] {r.text}"
    data = r.json()
    answer = data.get("textResponse") or f"(空回答: {data.get('error','无')})"
    sources = data.get("sources", [])
    if sources:
        titles = "\n".join(
            f"- {s.get('title') or s.get('docTitle') or '未命名'}"
            for s in sources
        )
        return f"{answer}\n\n来源:\n{titles}"
    return answer


if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=PORT)
