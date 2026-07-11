"""창업 법령 MCP 서버 (로컬 stdio 엔트리포인트).

Claude Desktop 등 MCP 클라이언트에서 로컬 실행. 도구 정의는 register_tools()
한 곳에 모아 v2 원격 HTTP 엔트리포인트가 공유할 수 있게 한다.

연결 (Claude Desktop) — %APPDATA%\\Claude\\claude_desktop_config.json:
  {
    "mcpServers": {
      "startup-law": {
        "command": "python",
        "args": ["C:/절대/경로/server.py"]
      }
    }
  }
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

import law_search as ls

SERVER_INSTRUCTIONS = """한국 창업 관련 법령 검색·조회 서버입니다.

창업자가 부딪히는 핵심 법령 — 중소기업창업 지원법, 벤처기업법, 벤처투자법,
상법(회사), 부가가치세법, 조세특례제한법(창업 세액감면), 근로기준법,
특허·상표법, 개인정보 보호법, 전자상거래법 등 — 과 그 시행령·시행규칙의
조문을 다룹니다.

사용자가 창업·법인설립·세액감면·고용·지식재산·온라인 판매의 법적 근거를
물으면 반드시 이 서버의 도구를 사용하세요:
- search_law: 자연어 조문 검색 — 가장 먼저 사용
- get_article: 법령명 + 조문번호로 본문 전체 조회
- list_laws: 인덱싱된 법령 목록
- verify_citation: 답변·문서에 인용된 "○○법 제○조"의 실재 여부 검증
- find_references: 조문의 정방향·역방향 인용 관계

인덱싱된 법령에 한하며, 법적 자문이 아닌 조문 참조 도구입니다.
답변에는 조문 출처(citation)를 함께 제시하세요."""


def register_tools(mcp: FastMCP) -> None:
    """도구 등록 단일 지점 — 로컬 stdio와 (v2) 원격 HTTP가 공유."""

    @mcp.tool()
    def search_law(
        query: str,
        law_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 10,
        fuzzy: bool = False,
    ) -> list[dict]:
        """창업 관련 법령을 조문 단위로 검색 — 법령 질문의 첫 진입점.

        예: "창업 세액감면 요건", "법인 설립 등기", "벤처기업 확인",
        "근로계약서 명시사항", "통신판매업 신고".

        Args:
            query: 자연어 검색어
            law_type: 법종 필터 (법률/대통령령/총리령/부령)
            source: 법령명 부분일치 필터 (예: "조세특례제한법")
            limit: 반환 결과 수 (기본 10)
            fuzzy: 음절 bi-gram 부분 매칭 (정확 매칭이 없을 때)

        Returns:
            [{source, article, article_title, snippet, citation, score, ...}]
        """
        return ls.search(query, law_type=law_type, source=source,
                         limit=limit, fuzzy=fuzzy)

    @mcp.tool()
    def get_article(source: str, article: str) -> list[dict]:
        """법령명·조문번호로 조문 본문 전체 조회.

        Args:
            source: 법령명 부분일치 (예: "중소기업창업 지원법")
            article: 조문번호 (예: "제11조", "11", "15의2", "제15조의2")

        Returns:
            매칭 조문 배열 (body 필드에 전체 본문, effective_date에 시행일).
        """
        return ls.get_article(source, article)

    @mcp.tool()
    def list_laws(law_type: Optional[str] = None) -> list[dict]:
        """인덱싱된 창업 법령 목록 (법령명·법종·시행일·조문 수).

        Args:
            law_type: 법종 필터 (법률/대통령령/총리령/부령, 선택)
        """
        return ls.list_laws(law_type=law_type)

    @mcp.tool()
    def verify_citation(text: str) -> list[dict]:
        """텍스트 안의 모든 '{법령명} 제N조' 인용을 인덱스로 교차검증.

        LLM이 지어낸 가짜 조문(환각)을 잡을 때 사용. 각 인용을
        ok / content_mismatch(제목 환각) / not_found / unknown_source로 분류.

        Args:
            text: 검증할 한국어 텍스트 (여러 인용 혼재 가능)
        """
        return ls.verify_citation(text)

    @mcp.tool()
    def find_references(source: str, article: str, limit: int = 20,
                        include_mermaid: bool = False) -> dict:
        """대상 조문의 정방향(outgoing)·역방향(incoming) 인용 관계 그래프.

        법률↔시행령↔타법 인용을 추적한다. scope: same_law / cross_law / external.

        Args:
            source: 법령명 부분일치
            article: 조문번호 (예: "제9조", "15의2")
            limit: 각 방향 최대 결과 수
            include_mermaid: True면 flowchart 코드 동봉 (시각화용)
        """
        return ls.find_references(source, article, limit=limit,
                                  include_mermaid=include_mermaid)


mcp = FastMCP("startup-law", instructions=SERVER_INSTRUCTIONS)
register_tools(mcp)


if __name__ == "__main__":
    mcp.run()
