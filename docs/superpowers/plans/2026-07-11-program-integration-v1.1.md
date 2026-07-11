# startup-law-mcp v1.1 지원사업 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** K-Startup(창업진흥원) 지원사업(사업소개 + 현재 공고)을 기존 법령 서버에 통합 — MCP 도구 4개 추가 (5 → 9개).

**Architecture:** 법령 축과 동일 패턴의 지원사업 축을 나란히 추가. `program_sync.py`(공공데이터포털 API → `data/programs/*.json` 스냅샷) + `programs.py`(로드·상태계산·검색·조회, `law_search`의 tokenize/make_snippet 재사용) + `server.py` 확장. 공고 상태(upcoming/open/closing_soon/closed)는 저장하지 않고 조회 시점에 계산.

**Tech Stack:** Python 3.10+, 표준 라이브러리, FastMCP. 기존 v1.0 코드베이스(law_sync.py/law_search.py/server.py, pytest 54개) 위에 증축.

**스펙:** [docs/superpowers/specs/2026-07-11-program-integration-design.md](../specs/2026-07-11-program-integration-design.md)

## Global Constraints

- 표준 라이브러리만 (urllib, json, re, datetime, pathlib, argparse, os, sys). 런타임 의존성은 기존 `mcp` 하나 유지.
- 인증키는 환경변수 `DATA_GO_KR_KEY`로만 주입 (data.go.kr **Decoding 일반 인증키** — urlencode가 인코딩하므로 원문 키 사용). 커밋 파일 어디에도 키 금지.
- 정규화 레코드 스키마(14키) 고정: `id, kind, name, category, summary, target, target_age, years, region, apply_start, apply_end, org, contact, url`. `kind`는 `"공고"` 또는 `"사업소개"`. 날짜는 `YYYY-MM-DD` 또는 빈 문자열.
- **실제 API 필드명·엔드포인트는 Task 1 probe 리포트가 진실** — Task 2~3의 필드 매핑 코드는 probe 결과에 맞춰 조정하되, 정규화 스키마(출력)는 절대 불변.
- 공고 상태: `upcoming`(오늘<접수시작) / `open`(기간 내, 마감 8일↑) / `closing_soon`(기간 내, 마감 7일 이내) / `closed`(오늘>마감) / `unknown`(파싱불가). 상태 계산 함수는 `today: date` 주입 가능.
- 검색·목록 기본 동작은 closed 제외. 스냅샷 7일↑ 경과 시 결과에 warning 동봉.
- sync는 전체 수집 성공 후에만 파일 교체 (부분 덮어쓰기 금지).
- `data/programs/*.json`은 커밋 대상, `data/_cache/`는 gitignore(기존 유지).
- 모든 파일 I/O `encoding="utf-8"` 명시. NFC 정규화는 `law_search._nfc` 재사용.
- 커밋 conventional commits. 테스트 `python -m pytest` (Windows). 기존 54개 테스트 상시 통과 유지.

**사전 준비물 (Task 1부터 필요):** data.go.kr 회원가입 → "창업진흥원_K-Startup(사업소개,사업공고,콘텐츠 등)_조회서비스"(데이터셋 15125364) 활용신청 → 일반 인증키(Decoding). 환경변수 `DATA_GO_KR_KEY`.

---

### Task 1: API 클라이언트 + probe (실구조 확정)

**Files:**
- Create: `program_sync.py`
- Test: `tests/test_program_sync_utils.py`

**Interfaces:**
- Produces:
  - `program_sync._date_norm(s) -> str` — `"20260711"`/`"2026-07-11"`/`"2026.07.11"` → `"2026-07-11"`, 실패 시 `""`
  - `program_sync._s(v) -> str` — None-safe strip
  - `program_sync.fetch_page(key: str, target: str, page: int = 1, per_page: int = 100) -> dict` — target은 `"announcement"`/`"intro"`
  - 모듈 전역 `PROGRAMS_DIR`, `API_BASE`, `ENDPOINTS`
  - **probe 리포트**: 실제 응답 엔벨로프(totalCount/data 등)와 아이템 필드명 목록 — Task 2·3의 매핑 기준

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_program_sync_utils.py`:
```python
import program_sync


def test_date_norm_compact():
    assert program_sync._date_norm("20260711") == "2026-07-11"


def test_date_norm_variants():
    assert program_sync._date_norm("2026-07-11") == "2026-07-11"
    assert program_sync._date_norm("2026.07.11") == "2026-07-11"


def test_date_norm_invalid():
    assert program_sync._date_norm(None) == ""
    assert program_sync._date_norm("상시") == ""
    assert program_sync._date_norm("") == ""
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_program_sync_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'program_sync'`

- [ ] **Step 3: 구현**

`program_sync.py`:
```python
"""K-Startup(창업진흥원) 지원사업 동기화 파이프라인.

공공데이터포털 'K-Startup 조회서비스'에서 사업공고·사업소개를 받아
data/programs/*.json 스냅샷으로 저장한다.

사용:
  set DATA_GO_KR_KEY=발급키(Decoding)     (Windows) / export DATA_GO_KR_KEY=... (POSIX)
  python program_sync.py probe --target announcement   # 원시 응답 구조 확인
  python program_sync.py probe --target intro
  python program_sync.py sync                           # 전체 동기화 (Task 3에서 추가)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PROGRAMS_DIR = DATA / "programs"
API_BASE = "https://apis.data.go.kr/B552735/kisedKstartupService01"
ENDPOINTS = {
    "announcement": "getAnnouncementInformation01",
    "intro": "getBusinessInformation01",
}


def _key() -> str:
    k = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not k:
        sys.exit("환경변수 DATA_GO_KR_KEY가 없습니다. data.go.kr에서 "
                 "'창업진흥원_K-Startup 조회서비스' 활용신청 후 인증키(Decoding)를 설정하세요.")
    return k


def _s(v) -> str:
    return str(v or "").strip()


def _date_norm(s) -> str:
    """'20260711'/'2026-07-11'/'2026.07.11' → '2026-07-11'. 그 외 ''."""
    s = str(s or "").strip()
    m = re.fullmatch(r"(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "startup-law-mcp/1.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_page(key: str, target: str, page: int = 1, per_page: int = 100) -> dict:
    """한 페이지 조회. 응답 엔벨로프는 probe로 확정 (기대: totalCount/data[])."""
    qs = urllib.parse.urlencode({
        "serviceKey": key, "page": page, "perPage": per_page, "returnType": "json",
    })
    return _get_json(f"{API_BASE}/{ENDPOINTS[target]}?{qs}")


def cmd_probe(args: argparse.Namespace) -> None:
    """원시 응답을 눈으로 확인 — 필드명·엔벨로프가 코드 가정과 다르면 여기서 발견."""
    key = _key()
    data = fetch_page(key, args.target, page=1, per_page=5)
    out = DATA / "_cache" / f"probe_programs_{args.target}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"엔벨로프 키: {sorted(data.keys())}")
    items = data.get("data") or []
    if items:
        print(f"아이템 수: {len(items)}, 첫 아이템 필드: {sorted(items[0].keys())}")
    print(f"원시 응답 저장: {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("probe", help="API 원시 응답 확인")
    pp.add_argument("--target", choices=sorted(ENDPOINTS), required=True)
    pp.set_defaults(func=cmd_probe)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_program_sync_utils.py -v`
Expected: 3 passed. 전체: `python -m pytest tests/ -q` → 57 passed

- [ ] **Step 5: 실 probe 실행 (핵심 리스크 컨트롤)**

```bash
DATA_GO_KR_KEY=<키> python program_sync.py probe --target announcement
DATA_GO_KR_KEY=<키> python program_sync.py probe --target intro
```

- 404/서비스 오류면: [API 문서](https://www.data.go.kr/data/15125364/openapi.do)와 K-Startup 스웨거에서 실제 엔드포인트 경로를 확인해 `ENDPOINTS`(필요시 `API_BASE`)를 수정하고 재시도.
- 성공하면: **리포트에 기록** — ① 엔벨로프 키(totalCount·data 대응 필드), ② 공고 아이템의 전체 필드명과 각 필드의 의미(사업명·개요·지원대상·접수시작/종료·기관·연락처·URL·지원분야·지역·연령·업력에 해당하는 실제 키), ③ 사업소개 아이템의 전체 필드명, ④ 날짜 필드의 실제 포맷 예시. 이 기록이 Task 2~3의 필드 매핑 기준이 된다.
- `data/_cache/`는 gitignore — probe 산출물 커밋 금지.

- [ ] **Step 6: Commit**

```bash
git add program_sync.py tests/test_program_sync_utils.py
git commit -m "feat: K-Startup 조회서비스 클라이언트 + probe CLI"
```

---

### Task 2: 정규화 (normalize_announcement / normalize_intro)

**Files:**
- Modify: `program_sync.py` (함수 추가 — `fetch_page` 아래)
- Create: `tests/fixtures/sample_programs.json` (**Task 1 probe 원시 응답에서 공고 2건·사업소개 2건 발췌**)
- Test: `tests/test_program_normalize.py`

**Interfaces:**
- Consumes: `_s`, `_date_norm`, Task 1 probe 리포트(실 필드명)
- Produces: `program_sync.normalize_announcement(raw: dict) -> dict`, `program_sync.normalize_intro(raw: dict) -> dict` — 둘 다 Global Constraints의 14키 스키마 반환. Task 3 `sync()`가 호출.

- [ ] **Step 1: fixture 작성**

`tests/fixtures/sample_programs.json` — `data/_cache/probe_programs_*.json`에서 발췌 (실 데이터이므로 필드명이 곧 진실):
```json
{
 "announcement_items": [ /* probe 공고 응답의 data[]에서 2건 그대로 복사 */ ],
 "intro_items": [ /* probe 사업소개 응답의 data[]에서 2건 그대로 복사 */ ]
}
```
공고 2건 중 최소 1건은 접수종료일 필드가 채워진 것으로 고른다.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_program_normalize.py`:
```python
import json
import re
from pathlib import Path

import program_sync

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_KEYS = {"id", "kind", "name", "category", "summary", "target", "target_age",
                 "years", "region", "apply_start", "apply_end", "org", "contact", "url"}


def _fx():
    return json.loads((FIXTURES / "sample_programs.json").read_text(encoding="utf-8"))


def test_normalize_announcement_schema():
    for raw in _fx()["announcement_items"]:
        rec = program_sync.normalize_announcement(raw)
        assert set(rec) == EXPECTED_KEYS
        assert rec["kind"] == "공고"
        assert rec["name"]


def test_normalize_announcement_dates_iso():
    recs = [program_sync.normalize_announcement(r) for r in _fx()["announcement_items"]]
    dated = [r for r in recs if r["apply_end"]]
    assert dated, "fixture에 접수종료일 있는 공고가 최소 1건 필요"
    for r in dated:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["apply_end"])


def test_normalize_intro_schema():
    for raw in _fx()["intro_items"]:
        rec = program_sync.normalize_intro(raw)
        assert set(rec) == EXPECTED_KEYS
        assert rec["kind"] == "사업소개"
        assert rec["name"]


def test_normalize_intro_no_apply_dates():
    for raw in _fx()["intro_items"]:
        rec = program_sync.normalize_intro(raw)
        assert rec["apply_start"] == ""
        assert rec["apply_end"] == ""
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_program_normalize.py -v`
Expected: FAIL — `AttributeError: module 'program_sync' has no attribute 'normalize_announcement'`

- [ ] **Step 4: 구현** — `program_sync.py`의 `fetch_page` 아래에 추가.
**아래 `raw.get(...)` 키들은 가정값이다 — Task 1 probe 리포트의 실제 필드명으로 교체하라 (출력 스키마는 불변).** 사업소개에 접수기간 필드가 실재하더라도 `apply_start`/`apply_end`는 빈 문자열로 둔다 (제도 설명이므로 — 스펙 결정).

```python
def normalize_announcement(raw: dict) -> dict:
    """사업공고 원시 아이템 → 표준 레코드. 필드명은 probe 리포트 기준."""
    return {
        "id": _s(raw.get("pbanc_sn") or raw.get("id")),
        "kind": "공고",
        "name": _s(raw.get("biz_pbanc_nm") or raw.get("intg_pbanc_biz_nm")),
        "category": _s(raw.get("supt_biz_clsfc")),
        "summary": _s(raw.get("pbanc_ctnt")),
        "target": _s(raw.get("aply_trgt_ctnt") or raw.get("aply_trgt")),
        "target_age": _s(raw.get("biz_trgt_age")),
        "years": _s(raw.get("biz_enyy")),
        "region": _s(raw.get("supt_regin")),
        "apply_start": _date_norm(raw.get("pbanc_rcpt_bgng_dt")),
        "apply_end": _date_norm(raw.get("pbanc_rcpt_end_dt")),
        "org": _s(raw.get("pbanc_ntrp_nm") or raw.get("sprv_inst")),
        "contact": _s(raw.get("prch_cnpl_no")),
        "url": _s(raw.get("detl_pg_url") or raw.get("biz_gdnc_url")),
    }


def normalize_intro(raw: dict) -> dict:
    """사업소개 원시 아이템 → 표준 레코드. 필드명은 probe 리포트 기준."""
    return {
        "id": _s(raw.get("biz_sn") or raw.get("id")),
        "kind": "사업소개",
        "name": _s(raw.get("biz_nm") or raw.get("supt_biz_titl_nm")),
        "category": _s(raw.get("supt_biz_clsfc") or raw.get("biz_categori_cd_nm")),
        "summary": _s(raw.get("biz_intrd_info") or raw.get("biz_supt_ctnt")),
        "target": _s(raw.get("supt_trgt") or raw.get("biz_supt_trgt_info")),
        "target_age": "",
        "years": "",
        "region": "",
        "apply_start": "",
        "apply_end": "",
        "org": _s(raw.get("sprv_inst") or raw.get("biz_prch_dprt_nm")),
        "contact": _s(raw.get("prch_cnpl_no")),
        "url": _s(raw.get("detl_pg_url") or raw.get("biz_gdnc_url")),
    }
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_program_normalize.py tests/test_program_sync_utils.py -v`
Expected: 7 passed. 전체 61 passed.

- [ ] **Step 6: Commit**

```bash
git add program_sync.py tests/fixtures/sample_programs.json tests/test_program_normalize.py
git commit -m "feat: K-Startup 응답 정규화 — 14키 표준 레코드 (실응답 fixture)"
```

---

### Task 3: 페이지네이션 수집 + 원자적 스냅샷 (`sync`)

**Files:**
- Modify: `program_sync.py` (함수·CLI 추가)
- Test: `tests/test_program_sync.py`

**Interfaces:**
- Consumes: `fetch_page`, `normalize_announcement`, `normalize_intro`, `PROGRAMS_DIR`(호출 시점 전역 참조 — 테스트가 monkeypatch)
- Produces: `program_sync.fetch_all(key, target, per_page=100, max_pages=50) -> list[dict]`, `program_sync.sync(key: str) -> dict` — 반환 `{"announcements": int, "intros": int, "fetched_at": ISO}`. 스냅샷 파일 구조 `{"fetched_at": ISO, "count": n, "items": [...]}`. **전체 수집 성공 후에만 파일 쓰기.** Task 5 `sync_programs` 도구가 호출.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_program_sync.py` (fake 아이템의 필드명은 Task 1 probe 리포트의 실제 공고/소개 필드명을 사용하라 — 아래는 가정값):
```python
import json

import pytest

import program_sync


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(program_sync, "PROGRAMS_DIR", tmp_path / "programs")
    pages = {
        ("announcement", 1): {"totalCount": 3, "data": [
            {"biz_pbanc_nm": "A공고", "pbanc_rcpt_end_dt": "20260801"},
            {"biz_pbanc_nm": "B공고", "pbanc_rcpt_end_dt": "20260802"},
        ]},
        ("announcement", 2): {"totalCount": 3, "data": [
            {"biz_pbanc_nm": "C공고", "pbanc_rcpt_end_dt": "20260803"},
        ]},
        ("intro", 1): {"totalCount": 1, "data": [{"biz_nm": "예비창업패키지"}]},
    }

    def fake_page(key, target, page=1, per_page=100):
        return pages.get((target, page), {"totalCount": 0, "data": []})

    monkeypatch.setattr(program_sync, "fetch_page", fake_page)
    return tmp_path


def test_fetch_all_paginates(env):
    items = program_sync.fetch_all("k", "announcement", per_page=2)
    assert len(items) == 3


def test_sync_writes_snapshots(env):
    result = program_sync.sync("k")
    assert result["announcements"] == 3
    assert result["intros"] == 1
    ann = json.loads((env / "programs" / "announcements.json").read_text(encoding="utf-8"))
    assert ann["count"] == 3
    assert ann["fetched_at"]
    assert ann["items"][0]["kind"] == "공고"
    intro = json.loads((env / "programs" / "intros.json").read_text(encoding="utf-8"))
    assert intro["items"][0]["kind"] == "사업소개"


def test_sync_preserves_snapshot_on_failure(env, monkeypatch):
    program_sync.sync("k")  # 정상 스냅샷 생성
    before = (env / "programs" / "announcements.json").read_text(encoding="utf-8")

    def boom(key, target, page=1, per_page=100):
        raise RuntimeError("api down")

    monkeypatch.setattr(program_sync, "fetch_page", boom)
    with pytest.raises(RuntimeError):
        program_sync.sync("k")
    # 실패한 동기화가 기존 스냅샷을 건드리지 않아야 함 (원자성)
    assert (env / "programs" / "announcements.json").read_text(encoding="utf-8") == before
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_program_sync.py -v`
Expected: FAIL — `AttributeError: module 'program_sync' has no attribute 'fetch_all'`

- [ ] **Step 3: 구현** — `normalize_intro` 아래 추가, `main()`에 sync 서브커맨드 등록:

```python
def fetch_all(key: str, target: str, per_page: int = 100, max_pages: int = 50) -> list[dict]:
    """전 페이지 수집. totalCount 도달 또는 빈 배치에서 중단."""
    items: list[dict] = []
    page = 1
    while page <= max_pages:
        data = fetch_page(key, target, page=page, per_page=per_page)
        batch = data.get("data") or []
        if not batch:
            break
        items.extend(batch)
        total = int(data.get("totalCount") or 0)
        if total and len(items) >= total:
            break
        page += 1
    return items


def sync(key: str) -> dict:
    """공고·사업소개 전체 수집 → 스냅샷 교체. 전체 성공 시에만 파일을 쓴다."""
    from datetime import datetime, timezone

    ann_raw = fetch_all(key, "announcement")
    intro_raw = fetch_all(key, "intro")
    fetched_at = datetime.now(timezone.utc).isoformat()
    ann = [normalize_announcement(r) for r in ann_raw]
    intros = [normalize_intro(r) for r in intro_raw]
    PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    for fname, items in (("announcements.json", ann), ("intros.json", intros)):
        (PROGRAMS_DIR / fname).write_text(
            json.dumps({"fetched_at": fetched_at, "count": len(items), "items": items},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")
    print(f"동기화 완료: 공고 {len(ann)}건, 사업소개 {len(intros)}건")
    return {"announcements": len(ann), "intros": len(intros), "fetched_at": fetched_at}


def cmd_sync(_args: argparse.Namespace) -> None:
    sync(_key())
```

`main()`의 probe 서브커맨드 아래에 추가:
```python
    ps = sub.add_parser("sync", help="공고·사업소개 전체 동기화")
    ps.set_defaults(func=cmd_sync)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 64 passed

- [ ] **Step 5: Commit**

```bash
git add program_sync.py tests/test_program_sync.py
git commit -m "feat: 지원사업 페이지네이션 수집 + 원자적 스냅샷 sync"
```

---

### Task 4: 조회 모듈 (`programs.py`)

**Files:**
- Create: `programs.py`
- Create: `tests/fixtures/programs/announcements.json`, `tests/fixtures/programs/intros.json`
- Modify: `tests/conftest.py` (fixture 추가)
- Test: `tests/test_programs.py`

**Interfaces:**
- Consumes: `law_search.tokenize`, `law_search.make_snippet`, `law_search._nfc`
- Produces (Task 5 서버가 그대로 위임):
  - `programs.load_programs(use_cache=True) -> dict`, `programs.invalidate_cache() -> None`
  - `programs.program_status(item: dict, today: Optional[date] = None) -> str`
  - `programs.staleness_warning(data: dict, today: Optional[date] = None) -> Optional[str]`
  - `programs.search_programs(query, status=None, include_closed=False, limit=10, today=None) -> dict` — `{"results": [...], "warning": str|None}`
  - `programs.get_program(name, today=None) -> dict` — 부분일치 상세, 최대 5건
  - `programs.list_open_programs(limit=20, today=None) -> dict` — open/closing_soon/upcoming, 마감일 오름차순

- [ ] **Step 1: fixture 작성**

`tests/fixtures/programs/announcements.json` (기준일 2026-07-11에서 closing_soon/open/upcoming/closed 각 1건):
```json
{
 "fetched_at": "2026-07-10T00:00:00+00:00",
 "count": 4,
 "items": [
  {"id": "1", "kind": "공고", "name": "2026년 예비창업패키지 예비창업자 모집 공고",
   "category": "사업화", "summary": "혁신 기술 아이템을 보유한 예비창업자의 사업화를 지원합니다.",
   "target": "예비창업자", "target_age": "만 39세 이하", "years": "예비", "region": "전국",
   "apply_start": "2026-07-01", "apply_end": "2026-07-15",
   "org": "창업진흥원", "contact": "1357", "url": "https://www.k-startup.go.kr/1"},
  {"id": "2", "kind": "공고", "name": "2026년 초기창업패키지 창업기업 모집 공고",
   "category": "사업화", "summary": "업력 3년 이내 초기 창업기업의 성장을 지원합니다.",
   "target": "창업 3년 이내 기업", "target_age": "", "years": "3년 이내", "region": "전국",
   "apply_start": "2026-07-01", "apply_end": "2026-08-30",
   "org": "창업진흥원", "contact": "1357", "url": "https://www.k-startup.go.kr/2"},
  {"id": "3", "kind": "공고", "name": "글로벌 액셀러레이팅 프로그램 참가기업 모집",
   "category": "글로벌", "summary": "해외 진출을 준비하는 창업기업을 지원합니다.",
   "target": "창업 7년 이내 기업", "target_age": "", "years": "7년 이내", "region": "전국",
   "apply_start": "2026-08-01", "apply_end": "2026-08-20",
   "org": "창업진흥원", "contact": "1357", "url": "https://www.k-startup.go.kr/3"},
  {"id": "4", "kind": "공고", "name": "청년창업사관학교 16기 입교생 모집",
   "category": "교육", "summary": "청년 창업자를 위한 사관학교 입교생을 모집합니다.",
   "target": "만 39세 이하 청년 창업자", "target_age": "만 39세 이하", "years": "3년 이내", "region": "전국",
   "apply_start": "2026-05-01", "apply_end": "2026-06-30",
   "org": "중소벤처기업진흥공단", "contact": "055-751-9000", "url": "https://www.k-startup.go.kr/4"}
 ]
}
```

`tests/fixtures/programs/intros.json`:
```json
{
 "fetched_at": "2026-07-10T00:00:00+00:00",
 "count": 2,
 "items": [
  {"id": "i1", "kind": "사업소개", "name": "예비창업패키지",
   "category": "사업화", "summary": "예비창업자에게 사업화 자금(최대 1억원)과 창업교육·멘토링을 지원하는 제도입니다.",
   "target": "예비창업자", "target_age": "", "years": "", "region": "",
   "apply_start": "", "apply_end": "",
   "org": "창업진흥원", "contact": "1357", "url": "https://www.k-startup.go.kr/intro1"},
  {"id": "i2", "kind": "사업소개", "name": "TIPS(민간투자주도형 기술창업지원)",
   "category": "기술창업", "summary": "민간 운영사 투자와 연계해 기술창업팀에 R&D 자금을 지원하는 제도입니다.",
   "target": "기술창업팀", "target_age": "", "years": "", "region": "",
   "apply_start": "", "apply_end": "",
   "org": "중소벤처기업부", "contact": "", "url": "https://www.k-startup.go.kr/intro2"}
 ]
}
```

`tests/conftest.py` 끝에 추가 (기존 `index` fixture·`FIXTURES` 상수는 그대로 둠):
```python
@pytest.fixture
def programs_index(monkeypatch):
    import programs

    monkeypatch.setattr(programs, "PROGRAMS_DIR", FIXTURES / "programs")
    monkeypatch.setattr(programs, "_CACHE", None)
    return programs
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_programs.py`:
```python
from datetime import date

import programs

T = date(2026, 7, 11)


def test_program_status_boundaries():
    mk = lambda s, e: {"apply_start": s, "apply_end": e}
    assert programs.program_status(mk("2026-07-01", "2026-07-11"), T) == "closing_soon"  # 마감 당일
    assert programs.program_status(mk("2026-07-01", "2026-07-10"), T) == "closed"
    assert programs.program_status(mk("2026-07-01", "2026-07-18"), T) == "closing_soon"  # D-7
    assert programs.program_status(mk("2026-07-01", "2026-07-19"), T) == "open"          # D-8
    assert programs.program_status(mk("2026-07-12", "2026-08-01"), T) == "upcoming"
    assert programs.program_status({}, T) == "unknown"


def test_search_returns_announcement_and_intro(programs_index):
    r = programs.search_programs("예비창업패키지", today=T)
    kinds = {row["kind"] for row in r["results"]}
    assert kinds == {"공고", "사업소개"}
    assert r["warning"] is None  # 스냅샷 1일 경과 — 신선


def test_search_excludes_closed_by_default(programs_index):
    assert programs.search_programs("창업사관학교", today=T)["results"] == []
    rows = programs.search_programs("창업사관학교", include_closed=True, today=T)["results"]
    assert len(rows) == 1
    assert rows[0]["status"] == "closed"


def test_search_status_filter_announcements_only(programs_index):
    rows = programs.search_programs("창업", status="open", today=T)["results"]
    assert rows
    assert all(row["kind"] == "공고" and row["status"] == "open" for row in rows)


def test_list_open_sorted_by_deadline(programs_index):
    rows = programs.list_open_programs(today=T)["results"]
    assert len(rows) == 3  # closed 제외
    ends = [row["apply_end"] for row in rows]
    assert ends == sorted(ends)
    assert all(row["status"] in ("open", "closing_soon", "upcoming") for row in rows)
    assert rows[0]["d_day"] == 4  # 예비창업패키지, 07-15 마감


def test_get_program_detail(programs_index):
    r = programs.get_program("예비창업패키지", today=T)
    assert 1 <= len(r["results"]) <= 5
    first = r["results"][0]
    assert first["kind"] == "공고"
    assert first["status"] == "closing_soon"
    assert first["d_day"] == 4


def test_staleness_warning():
    old = {"fetched_at": "2026-07-01T00:00:00+00:00"}
    w = programs.staleness_warning(old, T)
    assert w is not None and "10일" in w
    assert programs.staleness_warning({"fetched_at": "2026-07-10T00:00:00+00:00"}, T) is None
    assert "없습니다" in programs.staleness_warning({}, T)
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_programs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'programs'`

- [ ] **Step 4: 구현**

`programs.py`:
```python
"""지원사업(K-Startup 공고·사업소개) 조회 모듈.

data/programs/*.json 스냅샷을 로드해 상태 계산·검색·조회를 제공한다.
토크나이저·스니펫·NFC는 law_search를 재사용한다. IDF는 미적용 —
공고 코퍼스는 수백 건 규모라 TF + 사업명 가중으로 충분.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import law_search as ls

ROOT = Path(__file__).resolve().parent
PROGRAMS_DIR = ROOT / "data" / "programs"
STALE_DAYS = 7
CLOSING_SOON_DAYS = 7

_CACHE: Optional[dict] = None


def invalidate_cache() -> None:
    global _CACHE
    _CACHE = None


def load_programs(use_cache: bool = True) -> dict:
    """{"announcements": [...], "intros": [...], "fetched_at": ISO|None}"""
    global _CACHE
    if use_cache and _CACHE is not None:
        return _CACHE
    out = {"announcements": [], "intros": [], "fetched_at": None}
    for field, fname in (("announcements", "announcements.json"),
                         ("intros", "intros.json")):
        p = PROGRAMS_DIR / fname
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        out[field] = data.get("items", [])
        fa = data.get("fetched_at")
        if fa and (out["fetched_at"] is None or fa < out["fetched_at"]):
            out["fetched_at"] = fa  # 더 오래된 쪽 기준으로 신선도 판단
    _CACHE = out
    return out


def _parse_date(s) -> Optional[date]:
    try:
        return date.fromisoformat(str(s or "").strip())
    except ValueError:
        return None


def program_status(item: dict, today: Optional[date] = None) -> str:
    """upcoming / open / closing_soon / closed / unknown."""
    today = today or date.today()
    end = _parse_date(item.get("apply_end"))
    if end is None:
        return "unknown"
    if today > end:
        return "closed"
    start = _parse_date(item.get("apply_start"))
    if start and today < start:
        return "upcoming"
    if (end - today).days <= CLOSING_SOON_DAYS:
        return "closing_soon"
    return "open"


def _d_day(item: dict, today: date) -> Optional[int]:
    end = _parse_date(item.get("apply_end"))
    return (end - today).days if end else None


def staleness_warning(data: dict, today: Optional[date] = None) -> Optional[str]:
    fa = data.get("fetched_at")
    if not fa:
        return "지원사업 데이터가 없습니다. sync_programs를 먼저 실행하세요."
    try:
        fetched = datetime.fromisoformat(fa).date()
    except ValueError:
        return None
    days = ((today or date.today()) - fetched).days
    if days >= STALE_DAYS:
        return f"지원사업 스냅샷이 {days}일 지났습니다. sync_programs로 갱신을 권장합니다."
    return None


_SEARCH_FIELDS = ("name", "category", "summary", "target", "region", "org")


def _searchable_text(item: dict) -> str:
    return " ".join(str(item.get(k, "")) for k in _SEARCH_FIELDS)


def _result_row(item: dict, status: Optional[str], today: date,
                snippet: str = "", score: float = 0.0) -> dict:
    row = {
        "kind": item.get("kind"),
        "name": item.get("name"),
        "category": item.get("category"),
        "target": item.get("target"),
        "region": item.get("region"),
        "org": item.get("org"),
        "apply_start": item.get("apply_start"),
        "apply_end": item.get("apply_end"),
        "url": item.get("url"),
    }
    if status is not None:
        row["status"] = status
        dd = _d_day(item, today)
        if dd is not None and status != "closed":
            row["d_day"] = dd
    if snippet:
        row["snippet"] = snippet
    if score:
        row["score"] = round(score, 2)
    return row


def search_programs(query: str, status: Optional[str] = None,
                    include_closed: bool = False, limit: int = 10,
                    today: Optional[date] = None) -> dict:
    today = today or date.today()
    data = load_programs()
    tokens = ls.tokenize(query)
    if not tokens:
        return {"results": [], "warning": staleness_warning(data, today)}
    scored: list[tuple[float, int, Optional[str], dict, str]] = []
    for group, is_ann in (("announcements", True), ("intros", False)):
        for it in data[group]:
            st = program_status(it, today) if is_ann else None
            if is_ann:
                if not include_closed and st == "closed":
                    continue
                if status and st != status:
                    continue
            elif status:
                continue  # status 필터는 공고 전용 — 사업소개 제외
            text = _searchable_text(it)
            sc = 0.0
            pos = -1
            for tok in tokens:
                if tok in str(it.get("name", "")):
                    sc += 5.0
                cnt = text.count(tok)
                if cnt:
                    sc += float(cnt)
                    p = text.find(tok)
                    if pos < 0 or p < pos:
                        pos = p
            if sc <= 0:
                continue
            scored.append((sc, pos, st, it, text))
    scored.sort(key=lambda r: r[0], reverse=True)
    results = [_result_row(it, st, today, snippet=ls.make_snippet(text, pos), score=sc)
               for sc, pos, st, it, text in scored[:limit]]
    return {"results": results, "warning": staleness_warning(data, today)}


def get_program(name: str, today: Optional[date] = None) -> dict:
    """이름 부분일치 상세 (전체 필드). 공고 우선, 최대 5건."""
    today = today or date.today()
    data = load_programs()
    q = ls._nfc(str(name)).strip()
    hits: list[dict] = []
    for group, is_ann in (("announcements", True), ("intros", False)):
        for it in data[group]:
            if q and q not in ls._nfc(str(it.get("name", ""))):
                continue
            full = dict(it)
            if is_ann:
                st = program_status(it, today)
                full["status"] = st
                dd = _d_day(it, today)
                if dd is not None and st != "closed":
                    full["d_day"] = dd
            hits.append(full)
    return {"results": hits[:5], "warning": staleness_warning(data, today)}


def list_open_programs(limit: int = 20, today: Optional[date] = None) -> dict:
    """모집 중·마감 임박·모집 예정 공고, 마감일 오름차순."""
    today = today or date.today()
    data = load_programs()
    rows = []
    for it in data["announcements"]:
        st = program_status(it, today)
        if st not in ("open", "closing_soon", "upcoming"):
            continue
        rows.append(_result_row(it, st, today))
    rows.sort(key=lambda r: r.get("apply_end") or "9999-12-31")
    return {"results": rows[:limit], "warning": staleness_warning(data, today)}
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 71 passed (64 + 7)

- [ ] **Step 6: Commit**

```bash
git add programs.py tests/test_programs.py tests/conftest.py tests/fixtures/programs
git commit -m "feat: 지원사업 조회 모듈 — 상태 계산·검색·D-day·신선도 경고"
```

---

### Task 5: MCP 도구 4개 추가 + SERVER_INSTRUCTIONS 갱신

**Files:**
- Modify: `server.py`
- Modify: `tests/test_server.py` (기존 테스트 2개를 아래 내용으로 교체)

**Interfaces:**
- Consumes: `programs.search_programs/get_program/list_open_programs/invalidate_cache`, `program_sync.sync`
- Produces: 도구 9개 등록된 `server.mcp` (기존 5 + `search_program`, `get_program`, `list_open_programs`, `sync_programs`)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_server.py` 전체를 다음으로 교체:

```python
import asyncio


def test_nine_tools_registered():
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws", "verify_citation",
                     "find_references", "search_program", "get_program",
                     "list_open_programs", "sync_programs"}


def test_instructions_mention_both_axes():
    import server

    assert "창업" in server.SERVER_INSTRUCTIONS
    assert "search_law" in server.SERVER_INSTRUCTIONS
    assert "search_program" in server.SERVER_INSTRUCTIONS
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — 도구 5개만 등록되어 set 불일치

- [ ] **Step 3: 구현** — `server.py` 수정 3곳:

① import에 추가 (`import law_search as ls` 아래):
```python
import program_sync
import programs as pg
```

② `SERVER_INSTRUCTIONS` 전체 교체:
```python
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

지원사업 자격요건의 법적 근거까지 물으면 두 축을 함께 사용해 통합 답변하세요
(예: 예비창업패키지 공고 + 중소기업창업 지원법의 창업자 정의 조문).
답변에는 출처(조문 citation 또는 공고 url)를 제시하고, 신청 전 K-Startup
원문 공고 확인을 안내하세요. 법적 자문이 아닌 참조 도구입니다."""
```

③ `register_tools()` 안, `find_references` 도구 아래에 추가:
```python
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
        return pg.search_programs(query, status=status,
                                  include_closed=include_closed, limit=limit)

    @mcp.tool()
    def get_program(name: str) -> dict:
        """지원사업 이름 부분일치 상세 조회 (전체 필드, 최대 5건).

        "예비창업패키지가 뭔데?" 같은 제도 질문에 사업소개+현재 공고를 함께 반환.

        Args:
            name: 사업명 부분일치 (예: "예비창업패키지", "TIPS")
        """
        return pg.get_program(name)

    @mcp.tool()
    def list_open_programs(limit: int = 20) -> dict:
        """지금 모집 중·마감 임박·모집 예정인 공고 목록 (마감일 순, D-day 포함).

        "지금 신청할 수 있는 지원사업 뭐 있어?"에 사용.

        Args:
            limit: 반환 결과 수 (기본 20)
        """
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 71 passed (test_server.py 2개는 교체이므로 총계 유지)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: 지원사업 MCP 도구 4개 + 법령·지원사업 통합 SERVER_INSTRUCTIONS"
```

---

### Task 6: 실데이터 동기화 + README 갱신 + 스모크

**Files:**
- Create: `data/programs/announcements.json`, `data/programs/intros.json` (동기화 산출물)
- Modify: `README.md`

**Interfaces:**
- Consumes: 전체 파이프라인. 환경변수 `DATA_GO_KR_KEY` 필요.

- [ ] **Step 1: 전체 동기화**

```bash
DATA_GO_KR_KEY=<키> python program_sync.py sync
```
Expected: 공고 수백 건 + 사업소개 수십 건. 0건이거나 오류면 probe로 원인 확인 (엔드포인트·키 문제 구분).

- [ ] **Step 2: 스모크 테스트** (실제 출력을 리포트에 그대로 싣는다)

```bash
python -c "import programs, json; r = programs.search_programs('예비창업'); print(r['warning']); [print(x['status'] if 'status' in x else x['kind'], x['name'], x.get('apply_end','')) for x in r['results'][:5]]"
python -c "import programs, json; print(json.dumps(programs.get_program('예비창업패키지')['results'][:2], ensure_ascii=False, indent=1))"
python -c "import programs; [print(x['status'], x.get('d_day'), x['name']) for x in programs.list_open_programs()['results'][:10]]"
```
Expected: 예비창업 관련 결과가 상태·마감일과 함께 나오고, warning은 None. 이상하면(전부 closed, 날짜 파싱 실패 등) 정규화·상태 계산을 디버깅.

- [ ] **Step 3: 데이터 커밋**

```bash
git add data/programs
git commit -m "data: K-Startup 지원사업 초기 동기화 (공고 + 사업소개)"
```

- [ ] **Step 4: README 갱신**

- 한 줄 소개에 지원사업 축 추가 ("창업 법령 + K-Startup 지원사업 통합 MCP")
- 인덱싱 범위에 지원사업 섹션 (공고·사업소개 실제 건수)
- 도구 표 5개 → 9개 (신규 4개 입력·반환 요약)
- 빠른 시작에 `DATA_GO_KR_KEY` 발급·설정 단계 추가 (법령 OC 키와 별개임을 명시)
- 사용 예시 2개 추가: "예비창업자 지원사업 뭐 있어?" → search_program, "예비창업패키지 자격요건의 법적 근거는?" → search_program + search_law 통합
- 현행성 유지 섹션에 sync_programs 설명 (스냅샷 + 7일 경고)
- 로드맵 재편: v1.1 지원사업 통합(완료 표시) → v1.2 창업 특화 3도구 → v1.3 GitHub Actions 주간 동기화 → v2.0 원격 배포
- 라이선스·출처에 창업진흥원(K-Startup)·공공데이터포털 추가 + "신청 전 원문 공고 확인" 면책

```bash
git add README.md
git commit -m "docs: README — 지원사업 통합 반영 (도구 9개, 로드맵 재편)"
```

- [ ] **Step 5: 최종 확인**

Run: `python -m pytest tests/ -q`
Expected: 71 passed. `git grep`으로 인증키 유출 없음 확인 (`git grep -i data_go_kr_key`는 env 참조 코드만 나와야 함, 키 값 자체는 0건).
