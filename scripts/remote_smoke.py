"""원격 MCP 서버 스모크 — initialize → tools/list(12개) → search_law 실호출.

사용:  python scripts/remote_smoke.py http://127.0.0.1:8080/mcp
       python scripts/remote_smoke.py https://<앱>.fly.dev/mcp
"""
from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(url: str) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"tools({len(names)}):", ", ".join(names))
            assert len(names) == 12, "원격 표면은 12개여야 함"
            assert "sync_programs" not in names
            result = await session.call_tool(
                "search_law", {"query": "창업 세액감면", "limit": 3})
            text = str(result.content)[:300]
            print("search_law 응답 발췌:", text)
            assert "조세특례제한법" in text
    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
