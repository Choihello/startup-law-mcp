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

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

import law_search as ls
import program_sync
import programs as pg
import stages as st

SERVER_INSTRUCTIONS = """한국 창업 법령 + K-Startup 지원사업 통합 조회 서버입니다.

두 축을 다룹니다:
1) 창업 법령 — 중소기업창업 지원법, 벤처기업법, 조세특례제한법(창업 세액감면),
   근로기준법, 특허·상표법, 개인정보 보호법 등 50개 문서 8,000+ 조문
2) K-Startup 지원사업 — 예비창업패키지·초기창업패키지·TIPS 등 사업소개와
   현재 모집 공고(모집기간·지원대상·신청방법·D-day)

도구 선택:
- 지원사업·공고·모집·신청 질문("예비창업자 지원사업 뭐 있어?", "예비창업패키지
  지금 신청 되나?") → search_program / get_program / list_open_programs 먼저
- 법령·조문·자격요건의 법적 근거 질문 → search_law → get_article
- 인용 실재 검증 → verify_citation, 조문 인용 관계 → find_references
- 결과에 스냅샷 경고(warning)가 오면 → sync_programs로 갱신
- 데이터 상태·신선도·동기화 이력 확인 → data_status
- "이 법의 시행령 위임이 어디에 구체화됐나", 법↔시행령 연결·정비 점검 → delegation_map
- "창업 단계별로 뭘 봐야 하나", 단계별 조문+지원사업 가이드 → startup_stage_guide
- "이 조항 지금 시행 중인가", 시행일·경과조치 → check_effective_date

지원사업 자격요건의 법적 근거까지 물으면 두 축을 함께 사용해 통합 답변하세요
(예: 예비창업패키지 공고 + 중소기업창업 지원법의 창업자 정의 조문).
답변에는 출처(조문 citation 또는 공고 url)를 제시하고, 신청 전 K-Startup
원문 공고 확인을 안내하세요. 법적 자문이 아닌 참조 도구입니다."""

_VALID_STATUS = ("open", "closing_soon", "upcoming", "closed")
_FALLBACK_LAW_TYPES = ("법률", "대통령령", "총리령", "부령", "고용노동부령",
                       "재정경제부령", "중소벤처기업부령")


def _invalid(field: str, message: str) -> dict:
    return {"status": "invalid_input", "field": field, "message": message}


def _require_text(value, field: str) -> Optional[dict]:
    if not isinstance(value, str) or not value.strip():
        return _invalid(field, f"{field}은(는) 비어 있지 않은 문자열이어야 합니다.")
    return None


def _check_limit(limit, lo: int = 1, hi: int = 50) -> Optional[dict]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not lo <= limit <= hi:
        return _invalid("limit", f"limit은 {lo} 이상 {hi} 이하 정수여야 합니다.")
    return None


def _check_enum(value, field: str, allowed) -> Optional[dict]:
    if value is not None and value not in allowed:
        return _invalid(field, f"{field}은(는) {', '.join(sorted(allowed))} 중 하나여야 합니다.")
    return None


def _known_law_types():
    try:
        return {a.law_type for a in ls.load_index()} or set(_FALLBACK_LAW_TYPES)
    except RuntimeError:
        return set(_FALLBACK_LAW_TYPES)


def register_tools(mcp: FastMCP) -> None:
    """도구 등록 단일 지점 — 로컬 stdio와 (v2) 원격 HTTP가 공유."""

    @mcp.tool()
    def search_law(
        query: str,
        law_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 10,
        fuzzy: bool = False,
    ) -> list[dict] | dict:
        """창업 관련 법령을 조문 단위로 검색 — 법령 질문의 첫 진입점.

        예: "창업 세액감면 요건", "법인 설립 등기", "벤처기업 확인",
        "근로계약서 명시사항", "통신판매업 신고".

        Args:
            query: 자연어 검색어
            law_type: 법종 필터 — 인덱스의 실제 법종 값 사용 (법률/대통령령/총리령/고용노동부령 등, list_laws로 확인)
            source: 법령명 부분일치 필터 (예: "조세특례제한법")
            limit: 반환 결과 수 (기본 10)
            fuzzy: 음절 bi-gram 부분 매칭 (정확 매칭이 없을 때)

        Returns:
            [{source, article, article_title, snippet, citation, score, ...}]
        """
        err = _require_text(query, "query") or _check_limit(limit) or _check_enum(law_type, "law_type", _known_law_types())
        if err:
            return err
        return ls.search(query, law_type=law_type, source=source,
                         limit=limit, fuzzy=fuzzy)

    @mcp.tool()
    def get_article(source: str, article: str) -> list[dict] | dict:
        """법령명·조문번호로 조문 본문 전체 조회.

        Args:
            source: 법령명 부분일치 (예: "중소기업창업 지원법")
            article: 조문번호 (예: "제11조", "11", "15의2", "제15조의2")

        Returns:
            매칭 조문 배열 (body 필드에 전체 본문, effective_date에 시행일).
        """
        err = _require_text(source, "source") or _require_text(article, "article")
        if err:
            return err
        return ls.get_article(source, article)

    @mcp.tool()
    def list_laws(law_type: Optional[str] = None) -> list[dict] | dict:
        """인덱싱된 창업 법령 목록 (법령명·법종·시행일·조문 수).

        Args:
            law_type: 법종 필터 — 인덱스의 실제 법종 값 사용 (법률/대통령령/총리령/고용노동부령 등, list_laws로 확인, 선택)
        """
        err = _check_enum(law_type, "law_type", _known_law_types())
        if err:
            return err
        return ls.list_laws(law_type=law_type)

    @mcp.tool()
    def verify_citation(text: str) -> list[dict] | dict:
        """텍스트 안의 모든 '{법령명} 제N조' 인용을 인덱스로 교차검증.

        LLM이 지어낸 가짜 조문(환각)을 잡을 때 사용. 각 인용을
        ok / content_mismatch(제목 환각) / not_found / unknown_source로 분류.

        Args:
            text: 검증할 한국어 텍스트 (여러 인용 혼재 가능)
        """
        err = _require_text(text, "text")
        if err:
            return err
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
        err = _require_text(source, "source") or _require_text(article, "article") or _check_limit(limit)
        if err:
            return err
        return ls.find_references(source, article, limit=limit,
                                  include_mermaid=include_mermaid)

    @mcp.tool()
    def search_program(query: str, status: Optional[str] = None,
                       include_closed: bool = False, limit: int = 10) -> dict:
        """K-Startup 지원사업(공고+사업소개) 검색 — 지원사업 질문의 첫 진입점.

        예: "예비창업자 지원", "청년 창업 자금", "글로벌 진출", "R&D 지원".

        Args:
            query: 자연어 검색어
            status: 공고 상태 필터 (open/closing_soon/upcoming/closed).
                지정 시 공고만 반환 (사업소개 제외).
            include_closed: 마감 공고 포함 여부 (기본 False)
            limit: 반환 결과 수 (기본 10)

        Returns:
            {"results": [{kind, name, status?, d_day?, target, apply_end, url, ...}],
             "warning": 스냅샷 노후 경고 또는 None}
        """
        err = _require_text(query, "query") or _check_limit(limit) or _check_enum(status, "status", _VALID_STATUS)
        if err:
            return err
        return pg.search_programs(query, status=status,
                                  include_closed=include_closed, limit=limit)

    @mcp.tool()
    def get_program(name: str) -> dict:
        """지원사업 이름 부분일치 상세 조회 (전체 필드, 최대 5건).

        "예비창업패키지가 뭔데?" 같은 제도 질문에 사업소개+현재 공고를 함께 반환.

        Args:
            name: 사업명 부분일치 (예: "예비창업패키지", "TIPS")
        """
        err = _require_text(name, "name")
        if err:
            return err
        return pg.get_program(name)

    @mcp.tool()
    def list_open_programs(limit: int = 20) -> dict:
        """지금 모집 중·마감 임박·모집 예정인 공고 목록 (마감일 순, D-day 포함).

        "지금 신청할 수 있는 지원사업 뭐 있어?"에 사용.

        Args:
            limit: 반환 결과 수 (기본 20)
        """
        err = _check_limit(limit)
        if err:
            return err
        return pg.list_open_programs(limit=limit)

    @mcp.tool()
    def sync_programs() -> dict:
        """K-Startup에서 지원사업 공고·사업소개를 다시 받아 스냅샷 갱신.

        결과의 warning이 스냅샷 노후를 알리거나 사용자가 "지원사업 최신으로
        받아줘"라고 요청할 때 호출. 데이터만 갱신되므로 재시작이 필요 없습니다.
        환경변수 DATA_GO_KR_KEY(공공데이터포털 인증키)가 필요합니다.
        """
        import os

        key = os.environ.get("DATA_GO_KR_KEY", "").strip()
        if not key:
            return {"status": "error",
                    "message": "환경변수 DATA_GO_KR_KEY가 없습니다. data.go.kr에서 "
                               "'창업진흥원_K-Startup 조회서비스' 활용신청 후 "
                               "인증키(Decoding)를 설정하세요."}
        try:
            result = program_sync.sync(key)
        except Exception as e:  # noqa: BLE001 — 도구 표면에서 원인 전달
            return {"status": "error", "message": f"동기화 실패: {e}"}
        pg.invalidate_cache()
        return {"status": "ok", "restart_required": False, **result}

    @mcp.tool()
    def data_status() -> dict:
        """법령·지원사업 데이터 상태 한눈에 — 건수·수집 시각·신선도·경고.

        "데이터 상태 확인해줘", "동기화 언제 했지", "데이터 이상 없나" 요청 시 사용.
        """
        law: dict = {}
        try:
            arts = ls.load_index()
            law["source_count"] = len({a.source for a in arts})
            law["article_count"] = len(arts)
        except RuntimeError as e:
            law["error"] = str(e)
        src = ls.DATA / "sources.json"
        if src.exists():
            try:
                m = json.loads(src.read_text(encoding="utf-8"))
                law["manifest_count"] = m.get("count")
                law["sync_errors"] = len(m.get("errors", []))
                stale = [s.get("name") for s in m.get("sources", []) if s.get("stale")]
                if stale:
                    law["stale_sources"] = stale
            except json.JSONDecodeError:
                law["manifest_error"] = "sources.json 파싱 실패"
        pdata = pg.load_programs()
        return {
            "law": law,
            "programs": {
                "fetched_at": pdata.get("fetched_at"),
                "announcement_count": len(pdata["announcements"]),
                "intro_count": len(pdata["intros"]),
                "warnings": pg.data_warnings(pdata),
            },
        }

    @mcp.tool()
    def delegation_map(source: str, article: Optional[str] = None) -> dict:
        """법률↔시행령·시행규칙 위임 지도 + 정비 점검.

        "이 법 조문의 대통령령 위임이 시행령 어디에 구체화됐나"(법률 방향),
        "시행령 이 조문의 근거 법률 조문은?"(역방향), "시행령이 법 개정을
        따라왔나"(sync_check) 질문에 사용.

        Args:
            source: 법령명 부분일치 (법률·시행령·시행규칙 모두 가능)
            article: 특정 조문만 볼 때 (예: "제2조", 생략 시 전체 요약)
        """
        err = _require_text(source, "source")
        if err:
            return err
        if article is not None:
            err = _require_text(article, "article")
            if err:
                return err
        return ls.delegation_map(source, article=article)

    @mcp.tool()
    def startup_stage_guide(stage: Optional[str] = None) -> dict:
        """창업 단계별 가이드 — 단계마다 봐야 할 핵심 조문 + 지금 모집 중인 관련 지원사업.

        6단계: idea(아이디어 검증·예비창업) / incorporation(법인 설립) /
        funding(자금 조달) / hiring(첫 고용) / tax(세무·회계) / ip(지식재산·데이터).
        "창업하려는데 법적으로 뭘 봐야 해?", "법인 설립 단계 가이드" 질문에 사용.

        Args:
            stage: 단계 id 또는 이름 부분일치 (생략 시 6단계 개요)
        """
        if stage is not None:
            err = _require_text(stage, "stage")
            if err:
                return err
        try:
            return st.guide(stage)
        except RuntimeError as e:
            return {"error": str(e)}

    @mcp.tool()
    def check_effective_date(source: str, article: Optional[str] = None) -> dict:
        """법령·조문의 시행 상태 확인 — 시행 중/시행 예정(D-day)/부칙 경과조치.

        "이 조항 지금 시행 중이야?", "언제부터 적용돼?", "경과조치 있어?" 질문에 사용.

        Args:
            source: 법령명 부분일치
            article: 조문번호 (예: "제17조", 생략 시 법령 단위 판정)
        """
        err = _require_text(source, "source")
        if err:
            return err
        if article is not None:
            err = _require_text(article, "article")
            if err:
                return err
        return ls.check_effective_date(source, article=article)


mcp = FastMCP("startup-law", instructions=SERVER_INSTRUCTIONS)
register_tools(mcp)


if __name__ == "__main__":
    mcp.run()
