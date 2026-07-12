# startup-law-mcp v1.3 창업 특화 3도구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `delegation_map`(법률↔하위법령 위임 지도+정비 점검), `startup_stage_guide`(6단계 큐레이션+지원사업 연계), `check_effective_date`(시행일·경과조치) — 도구 10 → 13개.

**Architecture:** delegation·effective_date는 `law_search.py`에 조회 시점 실시간 스캔으로 추가(인덱스 스키마 불변). stage guide는 신규 소형 모듈 `stages.py` + `data/stages.json` 큐레이션 자산 — 법령(law_search)과 지원사업(programs)을 조합하는 책임이라 분리. 큐레이션 실재성은 pytest가 상시 검증.

**Tech Stack:** 기존과 동일 (Python 3.10+, 표준 라이브러리, mcp). 신규 의존성 없음.

**스펙:** [docs/superpowers/specs/2026-07-12-startup-tools-v1.3-design.md](../specs/2026-07-12-startup-tools-v1.3-design.md)

## Global Constraints

- 축약 참조 매칭: `(?<![가-힣])법 제N조(의M)` / `(?<![가-힣])영 제N조(의M)` — "○○법 제N조"(전체 이름)가 축약으로 오인되면 안 됨 (한글 lookbehind가 경계).
- 모법 해석은 이름 규칙만: `{모법} 시행령`/`{모법} 시행규칙` (인덱스 정확일치). 시행규칙의 "법"=모법, "영"=`{모법} 시행령`.
- sync_check는 Article.revision("시행 YYYY.MM.DD") 비교 — sources.json 의존 금지 (픽스처 테스트 호환).
- 날짜 판정 함수는 `today: Optional[date]` 주입 가능 (programs 관행). MCP 표면에는 today 미노출.
- v1.2 규약 유지: 입력 검증(_require_text, invalid_input), 표준 라이브러리만, NFC(ls._nfc), conventional commits, `python -m pytest`.
- **기존 105개 테스트 기대값 불변** — 픽스처 추가 텍스트는 기존 검색·refs·verify 단언을 흔들지 않는 본문으로 한정 (각 태스크에 영향 분석 주석 있음).
- stages.json의 모든 key_articles는 실재해야 하며 테스트가 검증 (실데이터 인덱스 없으면 skip). 미존재 조문은 조회 시 `missing: true`로 정직 표시 — 침묵 누락 금지.
- 보류 항목 구현 금지: 위임 엣지 사전 계산 인덱스, 조례·행정규칙, stage 업종 분기.

---

### Task 1: `delegation_map` (law_search.py)

**Files:**
- Modify: `law_search.py`, `tests/fixtures/대통령령_테스트창업법 시행령.md`
- Test: `tests/test_delegation.py` (신규)

**Interfaces:**
- Consumes: `load_index`, `_source_selector`, `_parse_article_token`, `_strip_meta`, `_around`, `Article`
- Produces (Task 4 서버가 위임):
  - `law_search.delegation_map(source: str, article: Optional[str] = None) -> dict`
  - 법률: `{"source", "role": "법률", "subordinates": [..], "delegating_articles": [{article, article_title, phrases, delegated_to: [{citation, article_title, snippet}]}], "counts", "sync_check"}`
  - 시행령/시행규칙: `{"source", "role", "parent", "articles_with_links": [{article, article_title, upward: [{citation, found, article_title, context}]}], "counts", "sync_check"}`
  - `law_search._revision_date(s) -> str` ("시행 2026.01.01"/"2026.01.01" → "2026-01-01", 실패 "") — Task 2도 사용

- [ ] **Step 1: 픽스처에 축약 참조 조문 추가**

`tests/fixtures/대통령령_테스트창업법 시행령.md`의 `### 제3조(세액감면 요건)` 블록 **뒤**(부칙 없음 — 파일 끝)에 추가:
```markdown

### 제4조(창업 범위)

법 제2조에 따른 창업기업의 범위는 중소벤처기업부장관이 고시한다.
```
(영향 분석: "세액감면"·"정의"·"테스트창업법" 문자열 없음 → 기존 검색·refs·verify 단언 무영향. list_laws의 시행령 조문 수는 어떤 테스트도 단언하지 않음.)

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_delegation.py`:

```python
import law_search as ls


def test_delegation_law_to_decree(index):
    r = ls.delegation_map("테스트창업법")
    assert r["role"] == "법률"
    assert r["subordinates"] == ["테스트창업법 시행령"]
    entries = {e["article"]: e for e in r["delegating_articles"]}
    assert "제2조" in entries  # "대통령령으로 정한다" 위임 문구 보유
    e = entries["제2조"]
    assert any("대통령령으로 정한" in p for p in e["phrases"])
    cites = [d["citation"] for d in e["delegated_to"]]
    assert "테스트창업법 시행령 제4조" in cites  # '법 제2조' 축약 역매칭


def test_delegation_abbrev_boundary(index):
    # 시행령 제3조는 '테스트창업법 제2조'(전체 이름) 참조 — 축약 매칭에 잡히면 안 됨
    r = ls.delegation_map("테스트창업법", article="제2조")
    e = r["delegating_articles"][0]
    cites = [d["citation"] for d in e["delegated_to"]]
    assert "테스트창업법 시행령 제3조" not in cites


def test_delegation_reverse_direction(index):
    r = ls.delegation_map("테스트창업법 시행령")
    assert r["role"] == "시행령"
    assert r["parent"] == "테스트창업법"
    linked = {a["article"]: a for a in r["articles_with_links"]}
    assert "제4조" in linked
    up = linked["제4조"]["upward"][0]
    assert up["citation"] == "테스트창업법 제2조"
    assert up["found"] is True


def test_delegation_sync_check(monkeypatch):
    arts = [
        ls.Article(law_type="법률", source="갱신법", revision="시행 2026.06.01", file="f",
                   chapter="", article="제1조", article_no=1, article_sub=0,
                   article_title="목적", body="세부 사항은 대통령령으로 정한다."),
        ls.Article(law_type="대통령령", source="갱신법 시행령", revision="시행 2025.01.01",
                   file="f", chapter="", article="제1조", article_no=1, article_sub=0,
                   article_title="목적", body="법 제1조에 따른다."),
    ]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.delegation_map("갱신법")
    assert r["sync_check"]["status"] == "review_needed"


def test_delegation_unknown_source(index):
    assert "error" in ls.delegation_map("없는법")
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_delegation.py -v`
Expected: FAIL — `AttributeError: module 'law_search' has no attribute 'delegation_map'`

- [ ] **Step 4: 구현** — `law_search.py`의 `find_references`/`_mermaid_graph` 아래에 추가:

```python
# ===== 창업 특화: 위임 지도 =====

_DELEGATION_RE = re.compile(r"[^.\n]*(?:대통령령|총리령|[가-힣]+부령)으로 정한[^.\n]*")
_ABBREV_LAW_RE = re.compile(r"(?<![가-힣])법 제(\d+)조(?:의(\d+))?")
_ABBREV_DECREE_RE = re.compile(r"(?<![가-힣])영 제(\d+)조(?:의(\d+))?")


def _revision_date(s: str) -> str:
    """'시행 2026.01.01' 또는 '2026.01.01' → '2026-01-01'. 실패 시 ''."""
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", s or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _parent_of(source: str) -> Optional[str]:
    for suffix in (" 시행규칙", " 시행령"):
        if source.endswith(suffix):
            return source[: -len(suffix)]
    return None


def _subordinates_of(law_name: str, articles: list[Article]) -> list[str]:
    names = {a.source for a in articles}
    return [n for n in (f"{law_name} 시행령", f"{law_name} 시행규칙") if n in names]


def _sync_check(source: str, articles: list[Article]) -> dict:
    """모법·하위법령 시행일(revision) 대조 — 정비 지연 플래그."""
    law_name = _parent_of(source) or source

    def eff(src: str) -> str:
        a = next((x for x in articles if x.source == src), None)
        return _revision_date(a.revision) if a else ""

    law_eff = eff(law_name)
    subs = _subordinates_of(law_name, articles)
    if not subs:
        return {"status": "no_subordinate", "law_effective": law_eff}
    checks = []
    worst = "ok"
    for s in subs:
        s_eff = eff(s)
        st = "unknown"
        if law_eff and s_eff:
            st = "review_needed" if law_eff > s_eff else "ok"
        if st == "review_needed":
            worst = "review_needed"
        elif st == "unknown" and worst == "ok":
            worst = "unknown"
        checks.append({"subordinate": s, "effective": s_eff, "status": st})
    return {"status": worst, "law_effective": law_eff, "subordinates": checks}


def delegation_map(source: str, article: Optional[str] = None) -> dict:
    """법률↔하위법령 위임 지도 + 정비 점검.

    법률: 위임 문구('대통령령/총리령/○○부령으로 정한다') 조문마다 하위법령의
    '법 제N조' 축약 참조를 역매칭. 시행령·시행규칙: 각 조문의 '법/영 제N조'를
    상위 조문으로 연결. sync_check는 시행일(revision) 대조.
    """
    articles = load_index()
    src_ok = _source_selector(source, articles)
    mine = [a for a in articles if src_ok(a.source) and not a.is_supplementary]
    if not mine:
        return {"error": f"대상 법령 없음: {source}"}
    real_source = mine[0].source
    mine = [a for a in mine if a.source == real_source]
    if article is not None:
        parsed = _parse_article_token(article)
        if parsed is None:
            return {"error": f"조문 토큰 해석 불가: {article!r}"}
        mine = [a for a in mine if (a.article_no, a.article_sub) == parsed]

    parent = _parent_of(real_source)
    if parent is None:
        subs = _subordinates_of(real_source, articles)
        refmap: dict[tuple[int, int], list[Article]] = {}
        for a in articles:
            if a.source not in subs or a.is_supplementary:
                continue
            for m in _ABBREV_LAW_RE.finditer(a.body):
                refmap.setdefault((int(m.group(1)), int(m.group(2) or 0)), []).append(a)
        entries = []
        for a in mine:
            phrases = [_strip_meta(p.strip()) for p in _DELEGATION_RE.findall(a.body)]
            if not phrases:
                continue
            seen: set[str] = set()
            delegated = []
            for t in refmap.get((a.article_no, a.article_sub), []):
                if t.citation in seen:
                    continue
                seen.add(t.citation)
                delegated.append({
                    "citation": t.citation,
                    "article_title": t.article_title,
                    "snippet": _strip_meta(t.body[:200].replace("\n", " "))[:120],
                })
            entries.append({"article": a.article, "article_title": a.article_title,
                            "phrases": phrases[:5], "delegated_to": delegated})
        result = {
            "source": real_source, "role": "법률", "subordinates": subs,
            "delegating_articles": entries,
            "counts": {"delegating": len(entries),
                       "linked": sum(1 for e in entries if e["delegated_to"])},
        }
    else:
        is_rule = real_source.endswith(" 시행규칙")
        decree_name = f"{parent} 시행령"
        links = []
        for a in mine:
            found_refs: list[tuple[str, int, int, int]] = []
            for m in _ABBREV_LAW_RE.finditer(a.body):
                found_refs.append((parent, int(m.group(1)), int(m.group(2) or 0), m.start()))
            if is_rule:
                for m in _ABBREV_DECREE_RE.finditer(a.body):
                    found_refs.append((decree_name, int(m.group(1)), int(m.group(2) or 0),
                                       m.start()))
            if not found_refs:
                continue
            seen: set[str] = set()
            ups = []
            for up_src, no, sub, pos in found_refs:
                cite = f"{up_src} 제{no}조" + (f"의{sub}" if sub else "")
                if cite in seen:
                    continue
                seen.add(cite)
                target = next((x for x in articles
                               if x.source == up_src and x.article_no == no
                               and x.article_sub == sub and not x.is_supplementary), None)
                ups.append({"citation": cite, "found": target is not None,
                            "article_title": target.article_title if target else None,
                            "context": _around(a.body, pos)})
            links.append({"article": a.article, "article_title": a.article_title,
                          "upward": ups})
        result = {
            "source": real_source,
            "role": "시행규칙" if is_rule else "시행령",
            "parent": parent, "articles_with_links": links,
            "counts": {"linked_articles": len(links)},
        }
    result["sync_check"] = _sync_check(real_source, articles)
    return result
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_delegation.py -v` → 5 passed. 전체: `python -m pytest tests/ -q` → 110 passed (기존 105 불변 확인 — 픽스처 영향 없음).

- [ ] **Step 6: Commit**

```bash
git add law_search.py tests/test_delegation.py "tests/fixtures/대통령령_테스트창업법 시행령.md"
git commit -m "feat: delegation_map — 위임 문구·축약 참조 역매칭 + 시행일 정비 점검"
```

---

### Task 2: `check_effective_date` (law_search.py)

**Files:**
- Modify: `law_search.py`, `tests/fixtures/법률_테스트창업법.md`
- Test: `tests/test_effective_date.py` (신규)

**Interfaces:**
- Consumes: `load_index`, `_source_selector`, `_parse_article_token`, `_around`, `_revision_date`(Task 1)
- Produces: `law_search.check_effective_date(source: str, article: Optional[str] = None, today: Optional[date] = None) -> dict` — `law: {status: in_force|upcoming|unknown, effective_date, d_day?}`, article 지정 시 `article: {citation, article_title, status, effective_date, d_day?, source_of_date: "article"|"law"}` + `transitional_provisions: [{supplementary, snippet}]`, source만이면 `latest_supplementary`. **law_search.py 상단 import에 `from datetime import date` 추가.**

- [ ] **Step 1: 픽스처 부칙에 경과조치 추가**

`tests/fixtures/법률_테스트창업법.md`의 부칙 블록 마지막 줄(`제1조(시행일) 이 법은 2026년 1월 1일부터 시행한다.`) **다음 줄**에 추가:
```markdown
제2조(경과조치) 이 법 시행 당시 종전의 제2조에 따라 창업한 기업은 개정 규정에 따른 창업기업으로 본다.
```
(영향 분석: 부칙은 블록 단위 1건(article_no=0)이라 조문 수 단언 불변. "세액감면"·"정의" 없음. 검색 단언 무영향 — "창업기업"은 어떤 law 검색 테스트의 질의도 아님. refs incoming은 부칙 제외.)

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_effective_date.py`:

```python
from datetime import date

import law_search as ls

T_BEFORE = date(2025, 12, 1)   # 시행일(2026-01-01) 전
T_AFTER = date(2026, 7, 12)


def test_law_level_in_force(index):
    r = ls.check_effective_date("테스트창업법", today=T_AFTER)
    assert r["law"]["status"] == "in_force"
    assert r["law"]["effective_date"] == "2026-01-01"
    assert "시행한다" in (r["latest_supplementary"]["effective_clause"] or "")


def test_law_level_upcoming_d_day(index):
    r = ls.check_effective_date("테스트창업법", today=T_BEFORE)
    assert r["law"]["status"] == "upcoming"
    assert r["law"]["d_day"] == 31


def test_article_level_with_transitional(index):
    r = ls.check_effective_date("테스트창업법", article="제2조", today=T_AFTER)
    assert r["article"]["status"] == "in_force"
    assert r["article"]["source_of_date"] == "law"  # 조문 <시행> 없음 → 법령 시행일 사용
    joined = " ".join(t["snippet"] for t in r["transitional_provisions"])
    assert "창업한 기업" in joined  # 부칙 경과조치 발췌


def test_article_effective_date_priority(monkeypatch):
    arts = [ls.Article(law_type="법률", source="갱신법", revision="시행 2026.01.01",
                       file="f", chapter="", article="제9조", article_no=9, article_sub=0,
                       article_title="특례", body="본문", effective_date="2026.12.01")]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.check_effective_date("갱신법", article="제9조", today=date(2026, 7, 12))
    assert r["article"]["status"] == "upcoming"
    assert r["article"]["source_of_date"] == "article"  # 조문 시행일이 법령 시행일에 우선


def test_effective_date_errors(index):
    assert "error" in ls.check_effective_date("없는법")
    assert "error" in ls.check_effective_date("테스트창업법", article="제99조")
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_effective_date.py -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 4: 구현** — import에 `from datetime import date` 추가 후, `delegation_map` 아래에:

```python
# ===== 창업 특화: 시행일·경과조치 =====

def _parse_iso(s) -> Optional[date]:
    try:
        return date.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


def check_effective_date(source: str, article: Optional[str] = None,
                         today: Optional[date] = None) -> dict:
    """법령·조문의 시행 상태(in_force/upcoming)와 부칙 경과조치를 확인."""
    today = today or date.today()
    articles = load_index()
    src_ok = _source_selector(source, articles)
    mine = [a for a in articles if src_ok(a.source)]
    if not mine:
        return {"error": f"대상 법령 없음: {source}"}
    real_source = mine[0].source
    mine = [a for a in mine if a.source == real_source]
    law_eff = _revision_date(mine[0].revision)

    def status_of(eff_iso: str) -> dict:
        d = _parse_iso(eff_iso)
        if d is None:
            return {"status": "unknown", "effective_date": eff_iso or None}
        if d > today:
            return {"status": "upcoming", "effective_date": eff_iso,
                    "d_day": (d - today).days}
        return {"status": "in_force", "effective_date": eff_iso}

    suppl = [a for a in mine if a.is_supplementary]
    result = {"source": real_source, "law": status_of(law_eff)}

    if article is None:
        if suppl:
            last = suppl[-1]
            m = re.search(r"제1조\(시행일\)[^\n]*", last.body)
            result["latest_supplementary"] = {
                "label": last.article,
                "effective_clause": m.group(0) if m else None,
            }
        return result

    parsed = _parse_article_token(article)
    if parsed is None:
        return {"error": f"조문 토큰 해석 불가: {article!r}"}
    no, sub = parsed
    target = next((a for a in mine if a.article_no == no and a.article_sub == sub
                   and not a.is_supplementary), None)
    if target is None:
        return {"error": f"조문 없음: {real_source} 제{no}조" + (f"의{sub}" if sub else "")}

    art_eff_iso = _revision_date(target.effective_date) if target.effective_date else law_eff
    result["article"] = {
        "citation": target.citation,
        "article_title": target.article_title,
        **status_of(art_eff_iso),
        "source_of_date": "article" if target.effective_date else "law",
    }
    label = f"제{no}조" + (f"의{sub}" if sub else "")
    trans = []
    for s in suppl:
        for m in re.finditer(re.escape(label), s.body):
            trans.append({"supplementary": s.article,
                          "snippet": _around(s.body, m.start(), span=90)})
    result["transitional_provisions"] = trans[:10]
    return result
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/ -q` → 115 passed (기존 불변 포함)

- [ ] **Step 6: Commit**

```bash
git add law_search.py tests/test_effective_date.py "tests/fixtures/법률_테스트창업법.md"
git commit -m "feat: check_effective_date — 시행 상태·D-day·부칙 경과조치 발췌"
```

---

### Task 3: `stages.py` 조회 모듈 (픽스처 기반)

**Files:**
- Create: `stages.py`, `tests/fixtures/stages_test.json`
- Test: `tests/test_stages.py` (신규)

**Interfaces:**
- Consumes: `law_search.get_article`, `law_search._nfc`, `programs.search_programs(query, limit, today)`
- Produces (Task 4 서버·Task 5 실데이터가 사용):
  - `stages.load_stages(use_cache=True) -> list[dict]`, `stages.STAGES_FILE`(모듈 전역, 테스트 monkeypatch), `stages._CACHE`
  - `stages.guide(stage: Optional[str] = None, today: Optional[date] = None) -> dict` — 생략 시 개요 `{"stages": [{id, order, name, summary, article_count}]}`, 지정 시 상세 `{id, name, summary, key_articles: [{citation, article_title?, why, missing?}], checklist, related_programs: [{query, why, results}], warning}`

- [ ] **Step 1: 테스트 픽스처 작성** — `tests/fixtures/stages_test.json`:

```json
{"stages": [
 {"id": "idea", "order": 1, "name": "아이디어 검증", "summary": "예비창업 준비 단계",
  "key_articles": [
    {"source": "테스트창업법", "article": "제2조", "why": "창업기업 정의"},
    {"source": "테스트창업법", "article": "제99조", "why": "존재하지 않는 조문(테스트)"}],
  "checklist": ["아이템 검증", "시장 조사"],
  "program_hints": [{"query": "예비창업", "why": "예비창업자 대상"}]},
 {"id": "incorporation", "order": 2, "name": "법인 설립", "summary": "설립 절차",
  "key_articles": [{"source": "테스트창업법 시행령", "article": "제2조", "why": "운영 절차"}],
  "checklist": ["정관 작성"],
  "program_hints": []}
]}
```

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_stages.py`:

```python
from datetime import date
from pathlib import Path

import pytest

import stages as st

FIXTURES = Path(__file__).parent / "fixtures"
T = date(2026, 7, 11)


@pytest.fixture
def stage_env(monkeypatch, index, programs_index):
    monkeypatch.setattr(st, "STAGES_FILE", FIXTURES / "stages_test.json")
    monkeypatch.setattr(st, "_CACHE", None)
    return st


def test_overview(stage_env):
    r = st.guide()
    assert [s["id"] for s in r["stages"]] == ["idea", "incorporation"]
    assert r["stages"][0]["article_count"] == 2


def test_detail_resolves_and_flags_missing(stage_env):
    r = st.guide("idea", today=T)
    arts = {a["citation"]: a for a in r["key_articles"]}
    assert arts["테스트창업법 제2조"]["article_title"] == "정의"
    missing = [a for a in r["key_articles"] if a.get("missing")]
    assert len(missing) == 1  # 제99조 — 침묵 누락 대신 정직 표시


def test_detail_partial_name_match(stage_env):
    assert st.guide("법인", today=T)["id"] == "incorporation"


def test_detail_includes_related_programs(stage_env):
    r = st.guide("idea", today=T)
    assert r["related_programs"][0]["query"] == "예비창업"
    names = [x["name"] for x in r["related_programs"][0]["results"]]
    assert any("예비창업패키지" in n for n in names)


def test_unknown_stage_error(stage_env):
    r = st.guide("우주정복")
    assert "error" in r and "idea" in r["error"]
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_stages.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stages'`

- [ ] **Step 4: 구현** — `stages.py`:

```python
"""창업 단계별 가이드 — data/stages.json 큐레이션 + 법령·지원사업 통합 조회.

법령 축(law_search)과 지원사업 축(programs)을 조합하는 모듈. 큐레이션의 조문
참조는 조회 시점에 인덱스로 실재 검증하며, 미존재 조문은 missing으로 정직 표시.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import law_search as ls
import programs as pg

ROOT = Path(__file__).resolve().parent
STAGES_FILE = ROOT / "data" / "stages.json"

_CACHE: Optional[list] = None


def load_stages(use_cache: bool = True) -> list[dict]:
    global _CACHE
    if use_cache and _CACHE is not None:
        return _CACHE
    if not STAGES_FILE.exists():
        raise RuntimeError("data/stages.json이 없습니다.")
    _CACHE = sorted(
        json.loads(STAGES_FILE.read_text(encoding="utf-8"))["stages"],
        key=lambda s: s.get("order", 0))
    return _CACHE


def stage_overview() -> dict:
    return {"stages": [{
        "id": s["id"], "order": s["order"], "name": s["name"],
        "summary": s["summary"], "article_count": len(s.get("key_articles", [])),
    } for s in load_stages()]}


def _find_stage(stage: str) -> Optional[dict]:
    q = ls._nfc(str(stage)).strip().lower()
    for s in load_stages():
        if s["id"] == q or q in ls._nfc(s["name"]):
            return s
    return None


def stage_detail(stage: str, program_limit: int = 3,
                 today: Optional[date] = None) -> dict:
    s = _find_stage(stage)
    if s is None:
        ids = [f'{x["id"]}({x["name"]})' for x in load_stages()]
        return {"error": f"단계 없음: {stage!r} — 사용 가능: {', '.join(ids)}"}
    resolved = []
    for ref in s.get("key_articles", []):
        hits = ls.get_article(ref["source"], ref["article"])
        if hits:
            h = hits[0]
            resolved.append({"citation": h["citation"],
                             "article_title": h["article_title"],
                             "why": ref.get("why", "")})
        else:
            resolved.append({"citation": f'{ref["source"]} {ref["article"]}',
                             "missing": True, "why": ref.get("why", "")})
    related = []
    warning = None
    for hint in s.get("program_hints", []):
        r = pg.search_programs(hint["query"], limit=program_limit, today=today)
        warning = warning or r.get("warning")
        related.append({"query": hint["query"], "why": hint.get("why", ""),
                        "results": r["results"]})
    return {"id": s["id"], "name": s["name"], "summary": s["summary"],
            "key_articles": resolved, "checklist": s.get("checklist", []),
            "related_programs": related, "warning": warning}


def guide(stage: Optional[str] = None, today: Optional[date] = None) -> dict:
    return stage_detail(stage, today=today) if stage else stage_overview()
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/ -q` → 120 passed

- [ ] **Step 6: Commit**

```bash
git add stages.py tests/test_stages.py tests/fixtures/stages_test.json
git commit -m "feat: stages 모듈 — 단계 큐레이션 조회 + 실재 검증 + 지원사업 live 연계"
```

---

### Task 4: 서버 3도구 등록 (10 → 13개)

**Files:**
- Modify: `server.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `ls.delegation_map`, `ls.check_effective_date`, `stages.guide`, v1.2 검증 헬퍼(`_require_text`)
- Produces: 도구 13개. `import stages as st`를 server import에 추가.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_server.py`의 `test_ten_tools_registered`를 교체하고 1개 추가:

```python
def test_thirteen_tools_registered():
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws", "verify_citation",
                     "find_references", "search_program", "get_program",
                     "list_open_programs", "sync_programs", "data_status",
                     "delegation_map", "startup_stage_guide", "check_effective_date"}


def test_instructions_mention_v13_tools():
    import server

    for t in ("delegation_map", "startup_stage_guide", "check_effective_date"):
        assert t in server.SERVER_INSTRUCTIONS
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: 교체·신규 2개 FAIL

- [ ] **Step 3: 구현** — `server.py`:

① import에 추가: `import stages as st`

② `SERVER_INSTRUCTIONS`의 도구 선택 목록(data_status 줄 다음)에 3줄 추가:
```
- "이 법의 시행령 위임이 어디에 구체화됐나", 법↔시행령 연결·정비 점검 → delegation_map
- "창업 단계별로 뭘 봐야 하나", 단계별 조문+지원사업 가이드 → startup_stage_guide
- "이 조항 지금 시행 중인가", 시행일·경과조치 → check_effective_date
```

③ `register_tools()` 안 `data_status` 아래에 3개 도구 추가:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q` → 121 passed (교체 1 ±0 + 신규 1)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: v1.3 도구 3개 등록 (13개) + SERVER_INSTRUCTIONS 안내"
```

---

### Task 5: 실데이터 stages.json 큐레이션 + 실재성 게이트 + README

**Files:**
- Create: `data/stages.json`, `tests/test_stages_data.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: 전체. 실데이터 인덱스(로컬 존재) — 이 태스크는 판단 작업이며, **모든 조문 번호는 작성 전 `python -X utf8 law_search.py get "<법령>" "<조문>"`으로 실재·내용을 확인**하고 확인 결과를 리포트에 남긴다.

- [ ] **Step 1: 실재성·구조 게이트 테스트 먼저 작성** — `tests/test_stages_data.py`:

```python
import json

import pytest

import law_search as ls
import stages as st


def test_real_stages_structure():
    if not st.STAGES_FILE.exists():
        pytest.skip("data/stages.json 없음")
    data = json.loads(st.STAGES_FILE.read_text(encoding="utf-8"))
    ids = [s["id"] for s in data["stages"]]
    assert ids == ["idea", "incorporation", "funding", "hiring", "tax", "ip"]
    for s in data["stages"]:
        assert 3 <= len(s["key_articles"]) <= 6
        assert s["summary"] and s["checklist"]
        assert all(r.get("why") for r in s["key_articles"])


def test_real_stages_articles_exist():
    if not ls.INDEX_FILE.exists():
        pytest.skip("실데이터 인덱스 없음 (CI 환경)")
    if not st.STAGES_FILE.exists():
        pytest.skip("data/stages.json 없음")
    data = json.loads(st.STAGES_FILE.read_text(encoding="utf-8"))
    missing = []
    for s in data["stages"]:
        for ref in s["key_articles"]:
            if not ls.get_article(ref["source"], ref["article"]):
                missing.append(f'{s["id"]}: {ref["source"]} {ref["article"]}')
    assert not missing, f"실재하지 않는 큐레이션 조문: {missing}"
```

- [ ] **Step 2: 큐레이션 작성** — `data/stages.json`

6단계(id 고정: idea/incorporation/funding/hiring/tax/ip), 단계당 key_articles 3~6개
(각각 `why` 한 줄 — 그 조문이 그 단계에서 왜 중요한지), checklist 3~5개, program_hints
1~2개(지원사업 스냅샷에서 실제로 결과가 나오는 검색어인지 `python -X utf8 -c
"import programs; print(len(programs.search_programs('<질의>')['results']))"`로 확인).

**후보 조문 (전부 get으로 검증 후 채택 — 어긋나면 인덱스에서 실제 조문을 찾아 교체):**
- idea: 중소기업창업 지원법 제2조(정의 — 창업·예비창업자·재창업), 중소기업기본법 제2조(중소기업자의 범위), 1인 창조기업 육성에 관한 법률 제2조(정의)
- incorporation: 상법 제169조(회사의 의의), 상법 제172조(회사의 성립), 부가가치세법 제8조(사업자등록), 중소기업창업 지원법의 창업 절차 간소화 관련 조문
- funding: 벤처투자 촉진에 관한 법률 제2조(정의 — 투자·조합), 벤처기업육성에 관한 특별법의 벤처기업 확인 조문, 조세특례제한법의 투자 관련 조문
- hiring: 근로기준법 제17조(근로조건의 명시), 근로기준법 제2조(정의 — 근로자·사용자), 고용보험법의 피보험자격 조문, 중소기업 인력지원 특별법 관련 조문
- tax: 조세특례제한법 제6조(창업중소기업 등에 대한 세액감면), 부가가치세법 제48조/제49조(예정·확정 신고) 계열, 부가가치세법 제61조(간이과세) 계열
- ip: 특허법 제87조(특허권의 설정등록) 계열, 상표법의 상표등록 조문, 부정경쟁방지 및 영업비밀보호에 관한 법률 제2조(정의), 개인정보 보호법 제15조(개인정보의 수집·이용)

- [ ] **Step 3: 게이트 통과 확인**

Run: `python -m pytest tests/test_stages_data.py -v` → 2 passed (skip 아님 — 로컬엔 인덱스 있음).
Run: `python -m pytest tests/ -q` → 123 passed
스모크: `python -X utf8 -c "import stages, json; print(json.dumps(stages.guide('tax'), ensure_ascii=False)[:600])"` — key_articles에 missing 없음, related_programs 결과 존재 확인 (실출력 리포트 수록).
추가 스모크: `python -X utf8 -c "import law_search as ls, json; r = ls.delegation_map('중소기업창업 지원법'); print(r['counts'], r['sync_check']['status'])"` — 위임 조문 다수 + linked > 0 확인.

- [ ] **Step 4: 커밋**

```bash
git add data/stages.json tests/test_stages_data.py
git commit -m "data: 창업 6단계 큐레이션 (조문 실재 검증 게이트 포함)"
```

- [ ] **Step 5: README 갱신 + 커밋**

- 도구 표: "도구 13개"로 제목 변경, "창업 특화 (3개, v1.3)" 표 추가 (`delegation_map` / `startup_stage_guide` / `check_effective_date` — 입력·반환 요약)
- 사용 예시 3개 추가: "중소기업창업 지원법의 시행령 위임 어디에 구체화됐어?" → delegation_map, "법인 설립 단계에서 봐야 할 법령이랑 지원사업 알려줘" → startup_stage_guide, "전자상거래법 이 조항 지금 시행 중이야?" → check_effective_date
- 데이터 구조에 `stages.json` 항목 추가 (창업 6단계 큐레이션 — 커밋 대상, 조문 실재성 테스트로 보증)
- 로드맵: v1.3 완료(현재) 표시 → v1.4 Actions 주간 동기화 → v2.0 원격

```bash
git add README.md
git commit -m "docs: README — 도구 13개·창업 특화 도구 사용 예시·로드맵 갱신"
```

- [ ] **Step 6: 최종 확인**

Run: `python -m pytest tests/ -q` → 123 passed. 키 리터럴 무존재 확인 (`git grep`이 전체 64자 키·이메일에 대해 exit 1).
