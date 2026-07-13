"""원격 HTTP 엔트리포인트 (Fly.io) — 읽기 전용 12개 도구.

sync_programs(관리)는 원격 공개판에서 제외한다. 데이터 갱신은 주간 동기화
PR 머지 → main push 자동 재배포(fly-deploy.yml)로 이뤄진다.

로컬 확인: python server_http.py  →  http://127.0.0.1:8080/mcp
검증:      python scripts/remote_smoke.py http://127.0.0.1:8080/mcp
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from server import SERVER_INSTRUCTIONS, register_tools

mcp = FastMCP("startup-law", instructions=SERVER_INSTRUCTIONS,
              host="0.0.0.0", port=8080, stateless_http=True)
register_tools(mcp, include_admin=False)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
