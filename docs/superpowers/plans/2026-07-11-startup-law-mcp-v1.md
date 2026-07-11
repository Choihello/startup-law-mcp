# startup-law-mcp v1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 창업 관련 한국 법령(~20개 법률 + 시행령·시행규칙)을 조문 단위로 검색·조회·검증하는 MCP 서버 v1.0 (기본 5도구 + 동기화 파이프라인 + CLI).

**Architecture:** [koica-reg-mcp](https://github.com/amnotyoung/koica-reg-mcp)의 4-파일 구조를 포팅. `law_sync.py`(국가법령정보센터 Open API → Format A 마크다운), `law_search.py`(조문 파서·인덱서·검색엔진·CLI), `server.py`(FastMCP stdio, register_tools 패턴). 데이터는 `data/laws/*.md` + `sources.json`, 빌드 산출물 `data/index.json`.

**Tech Stack:** Python 3.10+, FastMCP(`mcp` 패키지 — 유일한 런타임 의존성), pytest(개발용), 표준 라이브러리 검색엔진.

**스펙:** [docs/superpowers/specs/2026-07-11-startup-law-mcp-design.md](../specs/2026-07-11-startup-law-mcp-design.md)

## Global Constraints

- 런타임 의존성은 `mcp` 하나. 검색엔진·동기화는 표준 라이브러리만 (`urllib`, `json`, `re`, `unicodedata`, `math`, `dataclasses`, `pathlib`, `argparse`).
- 모든 한국어 문자열 비교 전 NFC 정규화 (`unicodedata.normalize("NFC", s)`).
- 법령 마크다운 파일명 규칙: `{법종}_{법령명}.md` (예: `법률_중소기업창업 지원법.md`, `대통령령_중소기업창업 지원법 시행령.md`).
- Open API 키는 환경변수 `LAW_OC`로만 주입 (코드·저장소에 키 하드코딩 금지).
- `data/index.json`, `data/_cache/`는 gitignore (빌드 산출물).
- 부칙(附則)은 본칙과 분리 태깅(`is_supplementary=True`) — 조번호 충돌 방지 (koica v2.2 교훈).
- 조회 도구는 본칙 우선: 본칙 매칭이 있으면 부칙 제외.
- 커밋 메시지는 conventional commits (`feat:`, `test:`, `chore:`, `docs:`).
- 테스트 실행 명령: `python -m pytest` (Windows 환경).

**사용자 사전 준비물 (Task 11 전까지 필요):** open.law.go.kr → OPEN API → 신청 → OC 키(이메일 ID 기반) 발급. Task 2~10은 fixture 기반이라 키 없이 진행 가능.

---

### Task 1: 프로젝트 스캐폴드

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.gitignore`, `data/laws.json`, `tests/__init__.py`

**Interfaces:**
- Produces: `data/laws.json` — 동기화 입력 큐레이션 목록. Task 4의 `sync()`가 읽는다. 스키마: `{"laws": [{"name": str, "group": str, "include_subordinate": bool(생략 시 true)}]}`

- [ ] **Step 1: 파일 생성**

`requirements.txt`:
```
mcp
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
```

`.gitignore`:
```
__pycache__/
.pytest_cache/
data/index.json
data/_cache/
*.pyc
```

`tests/__init__.py`: 빈 파일.

`data/laws.json` (초기 큐레이션 — 정확한 법령명은 Task 11에서 API 조회로 검증·보정):
```json
{
 "laws": [
  {"name": "중소기업창업 지원법", "group": "창업·벤처 코어"},
  {"name": "벤처기업육성에 관한 특별법", "group": "창업·벤처 코어"},
  {"name": "벤처투자 촉진에 관한 법률", "group": "창업·벤처 코어"},
  {"name": "1인 창조기업 육성에 관한 법률", "group": "창업·벤처 코어"},
  {"name": "중소기업기본법", "group": "창업·벤처 코어"},
  {"name": "소상공인 보호 및 지원에 관한 법률", "group": "창업·벤처 코어"},
  {"name": "중소기업 인력지원 특별법", "group": "창업·벤처 코어"},
  {"name": "상법", "group": "설립·운영"},
  {"name": "부가가치세법", "group": "설립·운영"},
  {"name": "조세특례제한법", "group": "설립·운영"},
  {"name": "근로기준법", "group": "고용"},
  {"name": "고용보험법", "group": "고용"},
  {"name": "산업재해보상보험법", "group": "고용"},
  {"name": "특허법", "group": "지재·데이터"},
  {"name": "상표법", "group": "지재·데이터"},
  {"name": "부정경쟁방지 및 영업비밀보호에 관한 법률", "group": "지재·데이터"},
  {"name": "개인정보 보호법", "group": "지재·데이터"},
  {"name": "전자상거래 등에서의 소비자보호에 관한 법률", "group": "온라인 사업"},
  {"name": "약관의 규제에 관한 법률", "group": "온라인 사업"}
 ]
}
```

- [ ] **Step 2: 의존성 설치 확인**

Run: `pip install -r requirements-dev.txt`
Expected: `mcp`, `pytest` 설치 성공 (이미 있으면 Requirement already satisfied).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: 프로젝트 스캐폴드 + 창업 법령 큐레이션 목록"
```

---

### Task 2: Open API 클라이언트 유틸 (`law_sync.py` 1부)

**Files:**
- Create: `law_sync.py`
- Test: `tests/test_sync_utils.py`

**Interfaces:**
- Produces:
  - `law_sync._as_list(v) -> list` — API의 dict-or-list 응답 정규화 (단건이 list로 안 감싸져 오는 국가법령정보센터 API 특성 대응)
  - `law_sync._fmt_date(s) -> str` — `"20260101"` → `"2026.01.01"`
  - `law_sync.fetch_law_list(oc: str, query: str) -> list[dict]` — lawSearch.do 법령 목록 (각 항목에 `법령명한글`, `법령일련번호` 키)
  - `law_sync.fetch_law(oc: str, mst: str) -> dict` — lawService.do 법령 본문 JSON

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_sync_utils.py`:
```python
import law_sync


def test_as_list_none():
    assert law_sync._as_list(None) == []


def test_as_list_single_dict():
    assert law_sync._as_list({"a": 1}) == [{"a": 1}]


def test_as_list_passthrough():
    assert law_sync._as_list([1, 2]) == [1, 2]


def test_fmt_date_yyyymmdd():
    assert law_sync._fmt_date("20260101") == "2026.01.01"
    assert law_sync._fmt_date(20241022) == "2024.10.22"


def test_fmt_date_passthrough():
    assert law_sync._fmt_date("2026.01.01") == "2026.01.01"
    assert law_sync._fmt_date(None) == ""
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_sync_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'law_sync'`

- [ ] **Step 3: 구현**

`law_sync.py`:
```python
"""국가법령정보센터 Open API 동기화 파이프라인.

data/laws.json(큐레이션 목록)의 법령을 open.law.go.kr API로 받아
Format A 마크다운(data/laws/*.md)과 매니페스트(data/sources.json)로 저장한다.

사용:
  set LAW_OC=발급받은키          (Windows) / export LAW_OC=... (POSIX)
  python law_sync.py probe --query "중소기업창업 지원법"   # API 응답 원본 확인
  python law_sync.py sync                                  # 전체 동기화
  python law_sync.py sync --only 창업                      # 이름 부분일치만
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
LAWS_DIR = DATA / "laws"
API_BASE = "https://www.law.go.kr/DRF"


def _oc() -> str:
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        sys.exit("환경변수 LAW_OC가 없습니다. open.law.go.kr에서 OC 키를 발급받아 설정하세요.")
    return oc


def _as_list(v) -> list:
    """API 응답의 dict-or-list 정규화. 단건은 list로 안 감싸져 온다."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _fmt_date(s) -> str:
    """'20260101' → '2026.01.01'. 이미 포맷됐거나 빈 값은 그대로/빈 문자열."""
    s = str(s or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}.{s[4:6]}.{s[6:]}"
    return s


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "startup-law-mcp/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_law_list(oc: str, query: str) -> list[dict]:
    """법령 목록 검색(현행). 각 항목: 법령명한글·법령일련번호(MST)·법령ID·시행일자 등."""
    q = urllib.parse.quote(query)
    url = f"{API_BASE}/lawSearch.do?OC={oc}&target=law&type=JSON&display=100&query={q}"
    data = _get_json(url)
    return _as_list((data.get("LawSearch") or {}).get("law"))


def fetch_law(oc: str, mst: str) -> dict:
    """법령 본문 조회. 반환 최상위 키: '법령' → 기본정보/조문/부칙."""
    url = f"{API_BASE}/lawService.do?OC={oc}&target=law&type=JSON&MST={mst}"
    return _get_json(url)


def cmd_probe(args: argparse.Namespace) -> None:
    """API 응답 원본을 눈으로 확인 — 실제 JSON 구조가 fixture와 다르면 여기서 발견한다."""
    oc = _oc()
    hits = fetch_law_list(oc, args.query)
    print(json.dumps(hits[:3], ensure_ascii=False, indent=1))
    if hits and args.full:
        mst = str(hits[0].get("법령일련번호", ""))
        law = fetch_law(oc, mst)
        out = DATA / "_cache" / f"probe_{mst}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(law, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"본문 JSON 저장: {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("probe", help="API 응답 원본 확인")
    pp.add_argument("--query", required=True)
    pp.add_argument("--full", action="store_true", help="첫 결과의 본문 JSON까지 저장")
    pp.set_defaults(func=cmd_probe)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_sync_utils.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add law_sync.py tests/test_sync_utils.py
git commit -m "feat: 국가법령정보센터 Open API 클라이언트 + probe CLI"
```

---

### Task 3: Format A 마크다운 변환기 (`law_to_markdown`)

**Files:**
- Modify: `law_sync.py` (함수 추가)
- Create: `tests/fixtures/sample_law.json`
- Test: `tests/test_law_to_markdown.py`

**Interfaces:**
- Consumes: `law_sync._as_list`, `law_sync._fmt_date`
- Produces: `law_sync.law_to_markdown(law_json: dict) -> tuple[str, dict]` — (Format A 마크다운, 메타 dict). 메타 키: `name, law_type, law_id, promulgation_no, promulgation_date, effective_date, ministry`. Task 4의 `sync()`와 Task 5의 파서가 이 마크다운 형식에 의존한다.

**Format A 규격** (Task 5 파서와의 계약):
```
# {법령명} ({법종} 제{공포번호}호, 시행 {시행일자})

- 법종: {법종}
- 공포일자: {공포일자}
- 시행일자: {시행일자}
- 소관부처: {소관부처}

## 제1장 총칙            ← 조문여부=="전문"인 조문단위 (장·절 헤더)

### 제1조(목적)           ← 조문. 가지번호는 "### 제2조의2(적용범위)"

<시행 2026.01.01>         ← 조문시행일자가 있으면 (선택)

{조문내용 + 항·호·목 평탄화, 줄바꿈 구분}

## 부칙 <제20517호, 2024.10.22>

{부칙내용 원문}
```

- [ ] **Step 1: fixture 작성**

`tests/fixtures/sample_law.json` — 국가법령정보센터 lawService.do 응답 축소판.
**주의:** 실제 API 응답 구조는 Task 11에서 `probe --full`로 검증한다. 구조가 다르면 이 fixture와 변환기를 실제 구조에 맞게 수정할 것 (필드명 후보: `법령명_한글`이 `법령명한글`일 수 있음, `법종구분`이 dict `{"content": ...}` 형태).
```json
{
 "법령": {
  "기본정보": {
   "법령ID": "001123",
   "법령명_한글": "테스트창업법",
   "공포일자": "20251201",
   "공포번호": "10000",
   "시행일자": "20260101",
   "법종구분": {"content": "법률"},
   "소관부처": {"content": "중소벤처기업부"}
  },
  "조문": {
   "조문단위": [
    {"조문번호": "1", "조문여부": "전문", "조문내용": "제1장 총칙"},
    {
     "조문번호": "1", "조문여부": "조문", "조문제목": "목적",
     "조문내용": "제1조(목적) 이 법은 창업기업의 성장을 촉진하여 국민경제 발전에 이바지함을 목적으로 한다.",
     "조문시행일자": "20260101"
    },
    {
     "조문번호": "2", "조문여부": "조문", "조문제목": "정의",
     "조문내용": "제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.",
     "항": [
      {
       "항번호": "①",
       "항내용": "① \"창업기업\"이란 창업하여 사업을 개시한 날부터 7년이 지나지 아니한 기업을 말한다.",
       "호": [
        {"호번호": "1.", "호내용": "1. 세액감면 요건은 대통령령으로 정한다."}
       ]
      }
     ]
    },
    {
     "조문번호": "2", "조문가지번호": "2", "조문여부": "조문", "조문제목": "적용범위",
     "조문내용": "제2조의2(적용범위) 제2조에 따른 창업기업에 대하여 적용한다."
    }
   ]
  },
  "부칙": {
   "부칙단위": [
    {
     "부칙공포일자": "20251201",
     "부칙공포번호": "10000",
     "부칙내용": ["부칙 <제10000호,2025.12.01.>", "제1조(시행일) 이 법은 2026년 1월 1일부터 시행한다."]
    }
   ]
  }
 }
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_law_to_markdown.py`:
```python
import json
from pathlib import Path

import law_sync

FIXTURES = Path(__file__).parent / "fixtures"


def _load():
    return json.loads((FIXTURES / "sample_law.json").read_text(encoding="utf-8"))


def test_header_and_meta():
    md, meta = law_sync.law_to_markdown(_load())
    assert md.startswith("# 테스트창업법 (법률 제10000호, 시행 2026.01.01)")
    assert "- 법종: 법률" in md
    assert "- 소관부처: 중소벤처기업부" in md
    assert meta["name"] == "테스트창업법"
    assert meta["law_type"] == "법률"
    assert meta["effective_date"] == "2026.01.01"


def test_chapter_and_articles():
    md, _ = law_sync.law_to_markdown(_load())
    assert "## 제1장 총칙" in md
    assert "### 제1조(목적)" in md
    assert "### 제2조의2(적용범위)" in md          # 가지번호
    assert "<시행 2026.01.01>" in md               # 조문시행일자


def test_hang_ho_flattened():
    md, _ = law_sync.law_to_markdown(_load())
    assert "\"창업기업\"이란" in md                 # 항내용
    assert "1. 세액감면 요건은 대통령령으로 정한다." in md   # 호내용


def test_supplementary_section():
    md, _ = law_sync.law_to_markdown(_load())
    assert "## 부칙 <제10000호, 2025.12.01>" in md
    assert "제1조(시행일) 이 법은 2026년 1월 1일부터 시행한다." in md
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_law_to_markdown.py -v`
Expected: FAIL — `AttributeError: module 'law_sync' has no attribute 'law_to_markdown'`

- [ ] **Step 4: 구현** — `law_sync.py`의 `fetch_law` 아래에 추가:

```python
def _content_of(v) -> str:
    """'법종구분': {'content': '법률'} 또는 평문자열 양쪽 대응."""
    if isinstance(v, dict):
        return str(v.get("content", "")).strip()
    return str(v or "").strip()


def _jo_label(unit: dict) -> str:
    """조문단위 → '제2조' / '제2조의2'."""
    no = int(str(unit.get("조문번호", "0")).strip() or 0)
    label = f"제{no}조"
    sub = str(unit.get("조문가지번호", "") or "").strip()
    if sub and sub != "0":
        label += f"의{int(sub)}"
    return label


def _unit_text(unit: dict) -> str:
    """조문단위 하나의 본문을 항·호·목까지 평탄화 (줄바꿈 구분)."""
    parts = [str(unit.get("조문내용", "") or "").strip()]
    for hang in _as_list(unit.get("항")):
        parts.append(str(hang.get("항내용", "") or "").strip())
        for ho in _as_list(hang.get("호")):
            parts.append(str(ho.get("호내용", "") or "").strip())
            for mok in _as_list(ho.get("목")):
                parts.append(str(mok.get("목내용", "") or "").strip())
    return "\n".join(p for p in parts if p)


def _flatten_text(v) -> str:
    """부칙내용 등 str/list 중첩 구조를 평탄화."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "\n".join(t for t in (_flatten_text(x) for x in v) if t)
    return str(v).strip()


def law_to_markdown(law_json: dict) -> tuple[str, dict]:
    """lawService.do JSON → (Format A 마크다운, 메타 dict)."""
    law = law_json.get("법령") or {}
    info = law.get("기본정보") or {}
    name = str(info.get("법령명_한글") or info.get("법령명한글") or "").strip()
    law_type = _content_of(info.get("법종구분")) or "법률"
    prom_no = str(info.get("공포번호", "")).strip()
    prom = _fmt_date(info.get("공포일자"))
    eff = _fmt_date(info.get("시행일자"))
    ministry = _content_of(info.get("소관부처"))

    lines = [
        f"# {name} ({law_type} 제{prom_no}호, 시행 {eff})",
        "",
        f"- 법종: {law_type}",
        f"- 공포일자: {prom}",
        f"- 시행일자: {eff}",
        f"- 소관부처: {ministry}",
        "",
    ]
    for unit in _as_list((law.get("조문") or {}).get("조문단위")):
        if str(unit.get("조문여부", "")).strip() != "조문":
            head = str(unit.get("조문내용", "") or "").strip()
            if head:
                lines += [f"## {head}", ""]
            continue
        title = str(unit.get("조문제목", "") or "").strip()
        head = f"### {_jo_label(unit)}({title})" if title else f"### {_jo_label(unit)}"
        lines += [head, ""]
        eff_jo = _fmt_date(unit.get("조문시행일자"))
        if eff_jo:
            lines += [f"<시행 {eff_jo}>", ""]
        body = _unit_text(unit)
        if body:
            lines += [body, ""]

    for buchik in _as_list((law.get("부칙") or {}).get("부칙단위")):
        b_no = str(buchik.get("부칙공포번호", "")).strip()
        b_date = _fmt_date(buchik.get("부칙공포일자"))
        text = _flatten_text(buchik.get("부칙내용"))
        lines += [f"## 부칙 <제{b_no}호, {b_date}>", ""]
        if text:
            lines += [text, ""]

    meta = {
        "name": name,
        "law_type": law_type,
        "law_id": str(info.get("법령ID", "")).strip(),
        "promulgation_no": prom_no,
        "promulgation_date": prom,
        "effective_date": eff,
        "ministry": ministry,
    }
    return "\n".join(lines).rstrip() + "\n", meta
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_law_to_markdown.py tests/test_sync_utils.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add law_sync.py tests/fixtures/sample_law.json tests/test_law_to_markdown.py
git commit -m "feat: lawService JSON → Format A 마크다운 변환기"
```

---

### Task 4: 동기화 오케스트레이션 (`sync`) + sources.json

**Files:**
- Modify: `law_sync.py` (함수·CLI 서브커맨드 추가)
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `fetch_law_list`, `fetch_law`, `law_to_markdown`, `DATA`, `LAWS_DIR` (모듈 전역 — 테스트에서 monkeypatch)
- Produces: `law_sync.sync(oc: str, only: str | None = None) -> dict` — 매니페스트 `{"count": int, "sources": [meta+file+mst+group+origin], "errors": [{"law","stage","error"}]}`. `data/sources.json`에 동일 내용 저장. **법령 단위 오류 격리** — 한 법령 실패가 전체를 중단시키지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_sync.py`:
```python
import json
from pathlib import Path

import pytest

import law_sync

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """DATA/LAWS_DIR을 tmp로 돌리고 laws.json·가짜 API를 세팅."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "laws.json").write_text(json.dumps({
        "laws": [
            {"name": "테스트창업법", "group": "테스트"},
            {"name": "존재하지않는법", "group": "테스트"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(law_sync, "DATA", data)
    monkeypatch.setattr(law_sync, "LAWS_DIR", data / "laws")

    sample = json.loads((FIXTURES / "sample_law.json").read_text(encoding="utf-8"))

    def fake_list(oc, query):
        if query == "테스트창업법":
            return [
                {"법령명한글": "테스트창업법", "법령일련번호": "111"},
                {"법령명한글": "테스트창업법 시행령", "법령일련번호": "222"},
                {"법령명한글": "전혀다른법", "법령일련번호": "999"},
            ]
        return []

    def fake_fetch(oc, mst):
        if mst == "111":
            return sample
        if mst == "222":
            dele = json.loads(json.dumps(sample))  # deep copy
            dele["법령"]["기본정보"]["법령명_한글"] = "테스트창업법 시행령"
            dele["법령"]["기본정보"]["법종구분"] = {"content": "대통령령"}
            return dele
        raise RuntimeError("unknown mst")

    monkeypatch.setattr(law_sync, "fetch_law_list", fake_list)
    monkeypatch.setattr(law_sync, "fetch_law", fake_fetch)
    return data


def test_sync_writes_md_and_manifest(env):
    result = law_sync.sync("dummy-oc")
    assert (env / "laws" / "법률_테스트창업법.md").exists()
    assert (env / "laws" / "대통령령_테스트창업법 시행령.md").exists()
    manifest = json.loads((env / "sources.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 2
    names = {s["name"] for s in manifest["sources"]}
    assert names == {"테스트창업법", "테스트창업법 시행령"}
    assert manifest["sources"][0]["origin"] == "law.go.kr"


def test_sync_isolates_errors(env):
    result = law_sync.sync("dummy-oc")
    # '존재하지않는법'은 목록 매칭 실패 → errors에 기록, 나머지는 정상 처리
    assert len(result["errors"]) == 1
    assert result["errors"][0]["law"] == "존재하지않는법"
    assert result["count"] == 2


def test_sync_only_filter(env):
    result = law_sync.sync("dummy-oc", only="창업")
    assert result["count"] == 2
    assert result["errors"] == []   # '존재하지않는법'은 필터로 스킵됨
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_sync.py -v`
Expected: FAIL — `AttributeError: module 'law_sync' has no attribute 'sync'`

- [ ] **Step 3: 구현** — `law_sync.py`의 `law_to_markdown` 아래에 추가하고 `main()`에 서브커맨드 등록:

```python
def sync(oc: str, only: str | None = None) -> dict:
    """laws.json 큐레이션 목록 전체를 동기화. 법령 단위 오류 격리."""
    curation = json.loads((DATA / "laws.json").read_text(encoding="utf-8"))
    LAWS_DIR.mkdir(parents=True, exist_ok=True)
    sources: list[dict] = []
    errors: list[dict] = []

    for entry in curation["laws"]:
        name = entry["name"]
        if only and only not in name:
            continue
        wanted = [name]
        if entry.get("include_subordinate", True):
            wanted += [f"{name} 시행령", f"{name} 시행규칙"]
        try:
            hits = fetch_law_list(oc, name)
        except Exception as e:  # noqa: BLE001 — 법령 단위 격리
            errors.append({"law": name, "stage": "search", "error": str(e)})
            continue
        by_name = {str(h.get("법령명한글", "")).strip(): h for h in hits}
        for w in wanted:
            hit = by_name.get(w)
            if not hit:
                if w == name:  # 본법 미발견만 오류 — 시행령·규칙은 없을 수 있음
                    errors.append({"law": w, "stage": "match",
                                   "error": "법령 목록에서 정확일치 결과 없음"})
                continue
            mst = str(hit.get("법령일련번호", "")).strip()
            try:
                md, meta = law_to_markdown(fetch_law(oc, mst))
                fname = f"{meta['law_type']}_{meta['name']}.md"
                (LAWS_DIR / fname).write_text(md, encoding="utf-8")
                meta.update({"file": fname, "mst": mst,
                             "group": entry.get("group", ""), "origin": "law.go.kr"})
                sources.append(meta)
                print(f"  ✓ {fname}")
            except Exception as e:  # noqa: BLE001
                errors.append({"law": w, "stage": "fetch", "error": str(e)})

    manifest = {"count": len(sources), "sources": sources, "errors": errors}
    (DATA / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"동기화 완료: {len(sources)}개 문서, 오류 {len(errors)}건")
    return manifest


def cmd_sync(args: argparse.Namespace) -> None:
    sync(_oc(), only=args.only)
```

`main()`의 probe 서브커맨드 아래에 추가:
```python
    ps = sub.add_parser("sync", help="laws.json 전체 동기화")
    ps.add_argument("--only", default=None, help="법령명 부분일치 필터")
    ps.set_defaults(func=cmd_sync)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add law_sync.py tests/test_sync.py
git commit -m "feat: 큐레이션 목록 동기화 오케스트레이션 + sources.json (오류 격리)"
```

---

### Task 5: 조문 파서·인덱서 (`law_search.py` 1부)

**Files:**
- Create: `law_search.py`
- Create: `tests/fixtures/법률_테스트창업법.md`, `tests/fixtures/대통령령_테스트창업법 시행령.md`, `tests/conftest.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Produces (이후 모든 태스크가 사용):
  - `law_search.Article` dataclass — 필드: `law_type: str, source: str, revision: str, file: str, chapter: str, article: str, article_no: int, article_sub: int, article_title: str, body: str, is_supplementary: bool = False, effective_date: str = ""`. 프로퍼티 `citation` = `f"{source} {article}"`
  - `law_search.parse_md(path: Path) -> list[Article]`
  - `law_search.build_index() -> list[Article]` — `data/laws/*.md` 전체 → `data/index.json`
  - `law_search.load_index(use_cache: bool = True) -> list[Article]` — 모듈 캐시 `_INDEX_CACHE`
  - `law_search._nfc(s: str) -> str`
- 테스트 인프라: `tests/conftest.py`의 `index` fixture — fixture md 2개를 파싱해 `_INDEX_CACHE`에 주입. Task 6~9의 모든 테스트가 이 fixture를 사용.

- [ ] **Step 1: fixture md 작성**

`tests/fixtures/법률_테스트창업법.md`:
```markdown
# 테스트창업법 (법률 제10000호, 시행 2026.01.01)

- 법종: 법률
- 공포일자: 2025.12.01
- 시행일자: 2026.01.01
- 소관부처: 중소벤처기업부

## 제1장 총칙

### 제1조(목적)

이 법은 창업기업의 성장을 촉진하여 국민경제 발전에 이바지함을 목적으로 한다.

### 제2조(정의)

이 법에서 "창업기업"이란 창업하여 사업을 개시한 날부터 7년이 지나지 아니한 기업을 말한다. 세액감면 요건은 대통령령으로 정한다.

### 제2조의2(적용범위)

제2조에 따른 창업기업에 대하여 적용한다. 「조세특례제한법」 제6조에 따른 감면은 별도로 한다.

## 부칙 <제10000호, 2025.12.01>

제1조(시행일) 이 법은 2026년 1월 1일부터 시행한다.
```

`tests/fixtures/대통령령_테스트창업법 시행령.md`:
```markdown
# 테스트창업법 시행령 (대통령령 제30000호, 시행 2026.01.01)

- 법종: 대통령령
- 공포일자: 2025.12.15
- 시행일자: 2026.01.01
- 소관부처: 중소벤처기업부

## 제1장 총칙

### 제3조(세액감면 요건)

테스트창업법 제2조에 따른 세액감면 요건은 다음 각 호와 같다.
1. 수도권과밀억제권역 외의 지역에서 창업할 것
```

`tests/conftest.py`:
```python
from pathlib import Path

import pytest

import law_search as ls

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def index(monkeypatch):
    arts = []
    for p in sorted(FIXTURES.glob("*.md")):
        arts.extend(ls.parse_md(p))
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    return arts
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_parse.py`:
```python
from pathlib import Path

import law_search as ls

FIXTURES = Path(__file__).parent / "fixtures"


def _law():
    return ls.parse_md(FIXTURES / "법률_테스트창업법.md")


def test_article_count():
    arts = _law()
    main = [a for a in arts if not a.is_supplementary]
    suppl = [a for a in arts if a.is_supplementary]
    assert len(main) == 3
    assert len(suppl) == 1


def test_metadata():
    a = _law()[0]
    assert a.source == "테스트창업법"
    assert a.law_type == "법률"
    assert a.revision == "시행 2026.01.01"
    assert a.chapter == "제1장 총칙"


def test_branch_number():
    arts = _law()
    a = next(x for x in arts if x.article == "제2조의2")
    assert a.article_no == 2
    assert a.article_sub == 2
    assert a.article_title == "적용범위"
    assert "창업기업에 대하여 적용한다" in a.body


def test_supplementary_tagged():
    arts = _law()
    s = next(x for x in arts if x.is_supplementary)
    assert s.article.startswith("부칙")
    assert "시행한다" in s.body
    assert s.article_no == 0


def test_citation_property():
    a = _law()[0]
    assert a.citation == "테스트창업법 제1조"


def test_index_fixture(index):
    assert {a.source for a in index} == {"테스트창업법", "테스트창업법 시행령"}
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'law_search'`

- [ ] **Step 4: 구현**

`law_search.py`:
```python
"""창업 법령 조문 인덱싱·검색 엔진 + CLI.

data/laws/*.md (Format A)를 조문 단위로 파싱해 data/index.json을 빌드하고,
검색·조회·인용검증·상호참조를 제공한다. 의존성: 표준 라이브러리만.

CLI:
  python law_search.py build
  python law_search.py search "창업 세액감면" --source 조세특례제한법
  python law_search.py get 테스트창업법 제2조
  python law_search.py verify "테스트창업법 제2조에 따라 ..."
  python law_search.py refs 테스트창업법 제2조
"""
from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LAWS_DIR = DATA / "laws"
INDEX_FILE = DATA / "index.json"


@dataclass
class Article:
    law_type: str
    source: str
    revision: str
    file: str
    chapter: str
    article: str
    article_no: int
    article_sub: int
    article_title: str
    body: str
    is_supplementary: bool = False
    effective_date: str = ""

    @property
    def citation(self) -> str:
        return f"{self.source} {self.article}"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


HEADER_RE = re.compile(r"^# (.+?) \((.+?), 시행 (.+?)\)\s*$")
CHAPTER_RE = re.compile(r"^## (?!부칙)(.+?)\s*$")
SUPPL_RE = re.compile(r"^## (부칙.*?)\s*$")
ARTICLE_HEAD_RE = re.compile(r"^### (제(\d+)조(?:의(\d+))?)(?:\((.*?)\))?\s*$")
_EFF_LINE_RE = re.compile(r"^<시행 (.+?)>\s*\n?")


def parse_md(path: Path) -> list[Article]:
    """Format A 마크다운 1개 파일 → Article 목록. 부칙은 블록 단위 1건으로 태깅."""
    text = _nfc(path.read_text(encoding="utf-8"))
    lines = text.split("\n")
    source = revision = law_type = ""
    m = HEADER_RE.match(lines[0]) if lines else None
    if m:
        source = m.group(1).strip()
        revision = "시행 " + m.group(3).strip()
    for ln in lines[1:10]:
        if ln.startswith("- 법종:"):
            law_type = ln.split(":", 1)[1].strip()

    articles: list[Article] = []
    chapter = ""
    in_suppl = False
    cur: Optional[tuple[str, int, int, str]] = None  # (article, no, sub, title)
    buf: list[str] = []
    suppl_label = ""
    suppl_buf: list[str] = []

    def flush_article() -> None:
        nonlocal cur, buf
        if cur:
            body = "\n".join(buf).strip()
            eff = ""
            em = _EFF_LINE_RE.match(body)
            if em:
                eff = em.group(1).strip()
                body = body[em.end():].lstrip("\n")
            articles.append(Article(
                law_type=law_type, source=source, revision=revision,
                file=path.name, chapter=chapter, article=cur[0],
                article_no=cur[1], article_sub=cur[2], article_title=cur[3],
                body=body, is_supplementary=False, effective_date=eff))
        cur, buf = None, []

    def flush_suppl() -> None:
        nonlocal suppl_label, suppl_buf
        if suppl_label:
            body = "\n".join(suppl_buf).strip()
            if body:
                articles.append(Article(
                    law_type=law_type, source=source, revision=revision,
                    file=path.name, chapter="부칙", article=suppl_label,
                    article_no=0, article_sub=0, article_title="부칙",
                    body=body, is_supplementary=True))
        suppl_label, suppl_buf = "", []

    for ln in lines[1:]:
        sm = SUPPL_RE.match(ln)
        if sm:
            flush_article()
            flush_suppl()
            in_suppl = True
            suppl_label = sm.group(1).strip()
            continue
        if in_suppl:
            suppl_buf.append(ln)
            continue
        cm = CHAPTER_RE.match(ln)
        if cm:
            flush_article()
            chapter = cm.group(1).strip()
            continue
        am = ARTICLE_HEAD_RE.match(ln)
        if am:
            flush_article()
            cur = (am.group(1), int(am.group(2)), int(am.group(3) or 0),
                   (am.group(4) or "").strip())
            continue
        if cur:
            buf.append(ln)
    flush_article()
    flush_suppl()
    return articles


def build_index() -> list[Article]:
    arts: list[Article] = []
    for p in sorted(LAWS_DIR.glob("*.md")):
        arts.extend(parse_md(p))
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps([asdict(a) for a in arts], ensure_ascii=False),
        encoding="utf-8")
    print(f"인덱스 빌드 완료: 문서 {len({a.source for a in arts})}개, 조문 {len(arts)}개")
    return arts


_INDEX_CACHE: Optional[list[Article]] = None


def load_index(use_cache: bool = True) -> list[Article]:
    global _INDEX_CACHE
    if use_cache and _INDEX_CACHE is not None:
        return _INDEX_CACHE
    if not INDEX_FILE.exists():
        raise RuntimeError(
            "인덱스가 없습니다. 먼저 `python law_search.py build`를 실행하세요.")
    names = {f.name for f in fields(Article)}
    data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    _INDEX_CACHE = [Article(**{k: v for k, v in d.items() if k in names}) for d in data]
    return _INDEX_CACHE


def cmd_build(_args: argparse.Namespace) -> None:
    build_index()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("build", help="data/laws/*.md → index.json")
    pb.set_defaults(func=cmd_build)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_parse.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add law_search.py tests/conftest.py tests/test_parse.py "tests/fixtures/법률_테스트창업법.md" "tests/fixtures/대통령령_테스트창업법 시행령.md"
git commit -m "feat: Format A 조문 파서 + 인덱스 빌드/로드 (부칙 분리 태깅)"
```

---

### Task 6: 검색 엔진 (tokenize·IDF·score·search)

**Files:**
- Modify: `law_search.py` (함수·CLI 추가)
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `Article`, `load_index`, `_nfc`, `index` fixture
- Produces:
  - `law_search.tokenize(query: str) -> list[str]`
  - `law_search.source_match(query: str, source_label: str) -> bool` — 3단계 부분일치 (직접 substring → 공백 토큰 전부 등장 → 공백·연결어 제거 정규화)
  - `law_search.search(query, law_type=None, source=None, limit=10, fuzzy=False) -> list[dict]` — 결과 dict 키: `law_type, source, revision, chapter, article, article_title, citation, snippet, score`
  - 내부: `compute_idf`, `_bigrams`, `score_article`, `make_snippet`, `_strip_meta`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_search.py`:
```python
import law_search as ls


def test_tokenize_strips_josa_and_stopwords():
    toks = ls.tokenize("창업기업의 세액감면 요건은 무엇")
    assert "창업기업" in toks   # 조사 "의" 제거
    assert "세액감면" in toks
    assert "요건" in toks       # 조사 "은" 제거
    assert "무엇" not in toks   # 불용어 제거


def test_search_finds_relevant_articles(index):
    results = ls.search("세액감면 요건")
    citations = [r["citation"] for r in results]
    assert "테스트창업법 시행령 제3조" in citations
    assert "테스트창업법 제2조" in citations
    assert all(r["score"] > 0 for r in results)


def test_search_source_filter(index):
    results = ls.search("세액감면", source="시행령")
    assert results
    assert all("시행령" in r["source"] for r in results)


def test_search_title_boost(index):
    # 조문제목 매칭("정의")이 본문-only 매칭보다 상위
    results = ls.search("정의")
    assert results[0]["citation"] == "테스트창업법 제2조"


def test_search_fuzzy_bigram(index):
    # 본문 표기는 "세액감면 요건"(공백) — 붙여 쓴 질의는 정확 매칭 실패,
    # fuzzy(음절 bi-gram)로만 잡힌다
    assert ls.search("세액감면요건", fuzzy=False) == []
    assert len(ls.search("세액감면요건", fuzzy=True)) >= 1


def test_source_match_normalization():
    assert ls.source_match("부정경쟁방지법", "부정경쟁방지 및 영업비밀보호에 관한 법률") is False  # 약칭은 v1 미지원 — 정직하게
    assert ls.source_match("부정경쟁방지", "부정경쟁방지 및 영업비밀보호에 관한 법률") is True
    assert ls.source_match("영업비밀 보호", "부정경쟁방지 및 영업비밀보호에 관한 법률") is True
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_search.py -v`
Expected: FAIL — `AttributeError: module 'law_search' has no attribute 'tokenize'`

- [ ] **Step 3: 구현** — `law_search.py`의 `load_index` 아래에 추가:

```python
STOPWORDS = {
    "다음", "중", "것", "것은", "것을", "어느", "어떤", "해당", "관한", "관하여",
    "대한", "대하여", "위한", "위하여", "그리고", "그러나", "또는", "다만", "각",
    "사항", "내용", "경우", "방법", "이상", "이하", "초과", "미만",
    "한다", "있다", "없다", "수", "또", "이", "무엇", "어떻게",
}

JOSA_RE = re.compile(
    r"(으로부터|에서의|으로써|이란|란|으로|로|의|를|을|은|는|이|가|과|와|에게|에서|에|도|만)$")


def tokenize(query: str) -> list[str]:
    query = _nfc(query)
    out: list[str] = []
    for tok in re.split(r"[\s,·、]+", query.strip()):
        tok = tok.strip("().,!?\"'·")
        if not tok:
            continue
        stripped = JOSA_RE.sub("", tok)
        candidate = stripped if len(stripped) >= 2 else tok
        if candidate in STOPWORDS or len(candidate) < 2:
            continue
        out.append(candidate)
    seen: set[str] = set()
    return [t for t in out if not (t in seen or seen.add(t))]


_SOURCE_CONNECTOR_RE = re.compile(r"에관한|관한|의|및|와|과|등에서의|등")


def _normalize_source(s: str) -> str:
    s = re.sub(r"[\s·․‧・]+", "", _nfc(s))
    return _SOURCE_CONNECTOR_RE.sub("", s)


def source_match(query: str, source_label: str) -> bool:
    """법령명 부분일치 (3단계): 직접 substring → 공백 토큰 전부 등장 → 정규화 substring."""
    if not query:
        return True
    q = _nfc(query).strip()
    s = _nfc(source_label)
    if not q:
        return True
    if q in s:
        return True
    tokens = [t for t in re.split(r"\s+", q) if len(t) >= 2]
    if tokens and all(t in s for t in tokens):
        return True
    nq = _normalize_source(q)
    if nq and nq in _normalize_source(s):
        return True
    return False


def compute_idf(tokens: list[str], articles: list[Article]) -> dict[str, float]:
    n = len(articles)
    idf: dict[str, float] = {}
    for t in tokens:
        df = sum(1 for a in articles
                 if t in a.body or t in a.article_title or t in a.chapter)
        idf[t] = math.log((n + 1) / (df + 1)) + 1.0
    return idf


def _bigrams(s: str) -> list[str]:
    return [s[i:i + 2] for i in range(len(s) - 1)]


def score_article(a: Article, tokens: list[str],
                  idf: Optional[dict[str, float]] = None,
                  fuzzy: bool = False) -> tuple[float, int]:
    score = 0.0
    first_pos = -1
    body = a.body
    for tok in tokens:
        w = idf[tok] if idf else 1.0
        if tok in a.article_title:
            score += 5.0 * w
        if tok in a.chapter:
            score += 2.0 * w
        cnt = body.count(tok)
        if cnt:
            score += float(cnt) * w
            pos = body.find(tok)
            if first_pos < 0 or pos < first_pos:
                first_pos = pos
        elif fuzzy and len(tok) >= 3:
            bgs = _bigrams(tok)
            hit_kinds = sum(1 for b in bgs if b in body)
            if hit_kinds >= len(bgs) * 0.5:
                bg_hits = sum(body.count(b) for b in bgs)
                score += (bg_hits / len(bgs)) * 0.3 * w
                if first_pos < 0:
                    for b in bgs:
                        p = body.find(b)
                        if p >= 0:
                            first_pos = p
                            break
    return score, first_pos


_META_NOISE_RE = re.compile(
    r"<(?:개정|신설|삭제|단서개정|제목개정|전부개정|시행)[^>]*?>"
    r"|\[(?:개정|신설|삭제|제목개정|단서개정|전부개정|전문개정)[^\]]*?\]")


def _strip_meta(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _META_NOISE_RE.sub("", text)).strip()


def make_snippet(body: str, pos: int, span: int = 80) -> str:
    if not body:
        return ""
    if pos < 0:
        s = _strip_meta(body[: span * 2].replace("\n", " "))
        return s + ("…" if len(body) > span * 2 else "")
    start = max(0, pos - span)
    end = min(len(body), pos + span)
    s = _strip_meta(body[start:end].replace("\n", " "))
    if start > 0:
        s = "…" + s
    if end < len(body):
        s = s + "…"
    return s


def search(query: str, law_type: Optional[str] = None,
           source: Optional[str] = None, limit: int = 10,
           fuzzy: bool = False) -> list[dict]:
    articles = load_index()
    tokens = tokenize(query)
    if not tokens:
        return []
    idf = compute_idf(tokens, articles)
    scored: list[tuple[float, int, Article]] = []
    for a in articles:
        if law_type and a.law_type != law_type:
            continue
        if source and not source_match(source, a.source):
            continue
        sc, pos = score_article(a, tokens, idf, fuzzy=fuzzy)
        if sc <= 0:
            continue
        scored.append((sc, pos, a))
    scored.sort(key=lambda r: r[0], reverse=True)
    return [{
        "law_type": a.law_type,
        "source": a.source,
        "revision": a.revision,
        "chapter": a.chapter,
        "article": a.article,
        "article_title": a.article_title,
        "citation": a.citation,
        "snippet": make_snippet(a.body, pos),
        "score": round(sc, 2),
    } for sc, pos, a in scored[:limit]]
```

`main()`에 search 서브커맨드 추가 (`cmd_build` 아래):
```python
def cmd_search(args: argparse.Namespace) -> None:
    for r in search(args.query, law_type=args.law_type, source=args.source,
                    limit=args.limit, fuzzy=args.fuzzy):
        print(f"[{r['score']:>6}] {r['citation']}({r['article_title']})")
        print(f"        {r['snippet']}")
```
```python
    psr = sub.add_parser("search", help="조문 검색")
    psr.add_argument("query")
    psr.add_argument("--law-type", dest="law_type", default=None)
    psr.add_argument("--source", default=None)
    psr.add_argument("--limit", type=int, default=10)
    psr.add_argument("--fuzzy", action="store_true")
    psr.set_defaults(func=cmd_search)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_search.py tests/test_parse.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add law_search.py tests/test_search.py
git commit -m "feat: IDF 가중 substring + 음절 bi-gram fuzzy 검색 엔진"
```

---

### Task 7: 조문 조회 (`get_article`) + 법령 목록 (`list_laws`)

**Files:**
- Modify: `law_search.py`
- Test: `tests/test_get.py`

**Interfaces:**
- Consumes: `Article`, `load_index`, `source_match`, `_nfc`
- Produces:
  - `law_search._parse_article_token(token: str) -> Optional[tuple[int, int]]` — `"제11조"`/`"11"`/`"15의2"`/`"제15조의2"` → `(11,0)`/`(15,2)`
  - `law_search._source_selector(query, articles)` — 정확일치 우선 술어 (Task 8·9도 사용)
  - `law_search.get_article(source: str, article: str) -> list[dict]` — dict 키: `law_type, source, revision, chapter, article, article_title, citation, body, effective_date, is_supplementary`
  - `law_search.list_laws(law_type: Optional[str] = None) -> list[dict]` — dict 키: `source, law_type, revision, article_count`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_get.py`:
```python
import law_search as ls


def test_parse_article_token_variants():
    assert ls._parse_article_token("제11조") == (11, 0)
    assert ls._parse_article_token("11") == (11, 0)
    assert ls._parse_article_token("15의2") == (15, 2)
    assert ls._parse_article_token("제15조의2") == (15, 2)
    assert ls._parse_article_token("별표1") is None


def test_get_article_exact(index):
    hits = ls.get_article("테스트창업법", "제2조의2")
    assert len(hits) == 1
    assert hits[0]["article_title"] == "적용범위"
    assert "창업기업에 대하여 적용한다" in hits[0]["body"]


def test_get_article_main_over_supplementary(index):
    # 본칙 제1조와 부칙 "제1조(시행일)"가 공존 — 본칙만 반환돼야 함
    hits = ls.get_article("테스트창업법", "제1조")
    assert len(hits) == 1
    assert hits[0]["is_supplementary"] is False
    assert hits[0]["article_title"] == "목적"


def test_get_article_exact_source_priority(index):
    # source가 '테스트창업법'과 정확일치하면 '테스트창업법 시행령'으로 번지지 않음
    hits = ls.get_article("테스트창업법", "제2조")
    assert {h["source"] for h in hits} == {"테스트창업법"}


def test_get_article_not_found(index):
    assert ls.get_article("테스트창업법", "제99조") == []


def test_list_laws(index):
    laws = ls.list_laws()
    by_source = {l["source"]: l for l in laws}
    assert by_source["테스트창업법"]["article_count"] == 4  # 본칙3 + 부칙1
    assert by_source["테스트창업법"]["law_type"] == "법률"
    only_decree = ls.list_laws(law_type="대통령령")
    assert [l["source"] for l in only_decree] == ["테스트창업법 시행령"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_get.py -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: 구현** — `law_search.py`의 `search` 아래에 추가:

```python
ARTICLE_TOKEN_RE = re.compile(r"^\s*(?:제)?(\d+)조?(?:의(\d+))?\s*$")


def _parse_article_token(token: str) -> Optional[tuple[int, int]]:
    t = _nfc(str(token)).strip()
    m = ARTICLE_TOKEN_RE.match(t)
    if m:
        return int(m.group(1)), int(m.group(2) or 0)
    m2 = re.search(r"제(\d+)조(?:의(\d+))?", t)
    if m2:
        return int(m2.group(1)), int(m2.group(2) or 0)
    return None


def _source_selector(query: Optional[str], articles: list[Article]):
    """법령명 매칭 술어. 정확일치(NFC)가 있으면 그 법령으로 한정 —
    '테스트창업법'이 '테스트창업법 시행령'까지 번지는 모호성 차단."""
    if not query:
        return lambda s: True
    q = _nfc(query).strip()
    if any(a.source == q for a in articles):
        return lambda s: s == q
    return lambda s: source_match(query, s)


def get_article(source: str, article: str) -> list[dict]:
    """법령명 매칭(정확일치 우선) + 조문번호 정확매칭. 본칙 우선."""
    parsed = _parse_article_token(article)
    if parsed is None:
        return []
    no, sub = parsed
    arts = load_index()
    src_ok = _source_selector(source, arts)
    matches = [a for a in arts
               if src_ok(a.source) and a.article_no == no and a.article_sub == sub]
    main = [a for a in matches if not a.is_supplementary]
    chosen = main if main else matches
    return [{
        "law_type": a.law_type,
        "source": a.source,
        "revision": a.revision,
        "chapter": a.chapter,
        "article": a.article,
        "article_title": a.article_title,
        "citation": a.citation,
        "body": a.body,
        "effective_date": a.effective_date,
        "is_supplementary": a.is_supplementary,
    } for a in chosen]


def list_laws(law_type: Optional[str] = None) -> list[dict]:
    by_src: dict[str, dict] = {}
    for a in load_index():
        if law_type and a.law_type != law_type:
            continue
        if a.source not in by_src:
            by_src[a.source] = {
                "source": a.source,
                "law_type": a.law_type,
                "revision": a.revision,
                "article_count": 0,
            }
        by_src[a.source]["article_count"] += 1
    return sorted(by_src.values(), key=lambda x: (x["law_type"], x["source"]))
```

주의: `test_get_article_main_over_supplementary`가 통과하려면 부칙 조문의 `article_no`가 0이어야 한다(Task 5에서 이미 그렇게 구현). 부칙 본문 안의 "제1조(시행일)"는 파싱 대상이 아니라 블록 body의 일부다.

`main()`에 get 서브커맨드 추가:
```python
def cmd_get(args: argparse.Namespace) -> None:
    for h in get_article(args.source, args.article):
        print(f"== {h['citation']}({h['article_title']}) [{h['revision']}]")
        print(h["body"])
```
```python
    pg = sub.add_parser("get", help="조문 본문 조회")
    pg.add_argument("source")
    pg.add_argument("article")
    pg.set_defaults(func=cmd_get)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -v`
Expected: 전체 통과 (30개)

- [ ] **Step 5: Commit**

```bash
git add law_search.py tests/test_get.py
git commit -m "feat: get_article(본칙 우선, 정확일치 소스) + list_laws"
```

---

### Task 8: 인용 검증 (`verify_citation`)

**Files:**
- Modify: `law_search.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `load_index`, `_nfc`, `_bigrams`, `_strip_meta`
- Produces: `law_search.verify_citation(text: str) -> list[dict]` — 각 인용의 `status`: `ok` / `content_mismatch`(제목 환각) / `not_found` / `unknown_source`. ok면 `article_title`·`body_excerpt`, not_found면 실제 조문 범위 안내 `message`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_verify.py`:
```python
import law_search as ls


def test_verify_ok(index):
    r = ls.verify_citation("테스트창업법 제2조에 따라 창업기업을 정의한다.")
    assert len(r) == 1
    assert r[0]["status"] == "ok"
    assert r[0]["citation"] == "테스트창업법 제2조"


def test_verify_ok_with_matching_title(index):
    r = ls.verify_citation("테스트창업법 제2조(정의)에 따르면")
    assert r[0]["status"] == "ok"
    assert r[0]["title_verified"] is True


def test_verify_content_mismatch(index):
    # 존재하는 조문번호 + 엉뚱한 제목 = 내용 환각
    r = ls.verify_citation("테스트창업법 제2조(창업지원센터 설치)에 따라")
    assert r[0]["status"] == "content_mismatch"
    assert r[0]["actual_title"] == "정의"


def test_verify_not_found(index):
    r = ls.verify_citation("테스트창업법 제99조에 따라")
    assert r[0]["status"] == "not_found"
    assert "제99조" in r[0]["citation"]
    assert "실재" in r[0]["message"]


def test_verify_unknown_source(index):
    r = ls.verify_citation("무명가상법 제1조에 따라")
    assert r[0]["status"] == "unknown_source"


def test_verify_definition_paren_not_title(index):
    # "(이하 ...)"는 제목이 아니라 부연 — 제목검증 제외, ok
    r = ls.verify_citation('테스트창업법 제2조(이하 "창업조항")에 따라')
    assert r[0]["status"] == "ok"
    assert r[0]["title_verified"] is False


def test_verify_multiple_citations(index):
    text = "테스트창업법 제1조와 테스트창업법 제99조를 근거로 한다."
    r = ls.verify_citation(text)
    statuses = [x["status"] for x in r]
    assert statuses == ["ok", "not_found"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_verify.py -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: 구현** — `law_search.py`의 `list_laws` 아래에 추가:

```python
CITATION_RE = re.compile(
    r"제(\d+)조(?:의(\d+))?(?:\s*제\d+항)?(?:\s*제\d+호)?(?:\s*\(([^)]{2,40})\))?")
_DEF_PAREN_RE = re.compile(r"이하|약칭|['\"‘’“”]|(?:이)?라\s*(?:한다|칭한다)")


def _title_key(s: str) -> str:
    return re.sub(r"[\s·․.,'\"()\[\]「」]", "", _nfc(s))


def _title_matches(cited: str, actual: str) -> bool:
    """인용 제목이 실제 제목의 부분(축약)이면 일치, 수식어를 덧붙였으면 환각.
    그 외 음절 bigram Jaccard ≥ 0.4면 이표기로 간주."""
    c, a = _title_key(cited), _title_key(actual)
    if not c or not a:
        return True
    if c == a or c in a:
        return True
    cb, ab = set(_bigrams(c)), set(_bigrams(a))
    if not cb or not ab:
        return True
    return len(cb & ab) / len(cb | ab) >= 0.4


def _article_range_for(source_nfc: str, articles: list[Article]) -> str:
    nos = sorted({(a.article_no, a.article_sub) for a in articles
                  if source_nfc in a.source and not a.is_supplementary})
    if not nos:
        return "(해당 법령 없음)"
    def lab(t):
        return f"제{t[0]}조" + (f"의{t[1]}" if t[1] else "")
    return f"{lab(nos[0])} ~ {lab(nos[-1])}, 총 {len(nos)}개"


def verify_citation(text: str) -> list[dict]:
    """텍스트 내 모든 '{법령명} 제N조[의M][(제목)]' 인용을 인덱스로 교차검증."""
    text_nfc = _nfc(text)
    articles = load_index()
    known_sources = sorted({a.source for a in articles}, key=len, reverse=True)

    def nearest_source(prefix: str) -> Optional[str]:
        best, best_pos = None, -1
        for src in known_sources:
            pos = prefix.rfind(src)
            if pos > best_pos or (pos == best_pos and best and len(src) > len(best)):
                best_pos, best = pos, src
        return best if best_pos >= 0 else None

    results = []
    for m in CITATION_RE.finditer(text_nfc):
        prefix = text_nfc[max(0, m.start() - 80): m.start()]
        matched_src = nearest_source(prefix)
        art = f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "")
        full_cite = text_nfc[m.start(): m.end()]
        if not matched_src:
            results.append({
                "citation": full_cite,
                "status": "unknown_source",
                "message": "직전 텍스트에서 인덱싱된 법령명을 찾지 못함",
            })
            continue
        no, sub = int(m.group(1)), int(m.group(2) or 0)
        cand = [a for a in articles
                if a.source == matched_src and a.article_no == no
                and a.article_sub == sub and not a.is_supplementary]
        hit = cand[0] if cand else None
        if hit:
            cited_title = (m.group(3) or "").strip()
            check_title = bool(cited_title) and not _DEF_PAREN_RE.search(cited_title)
            if check_title and not _title_matches(cited_title, hit.article_title):
                results.append({
                    "citation": f"{matched_src} {art}",
                    "raw_match": full_cite,
                    "status": "content_mismatch",
                    "cited_title": cited_title,
                    "actual_title": hit.article_title,
                    "message": f"{matched_src} {art}의 실제 제목은 '{hit.article_title}' — "
                               f"인용의 '{cited_title}'와 불일치 (내용 환각 가능)",
                })
            else:
                results.append({
                    "citation": f"{matched_src} {art}",
                    "raw_match": full_cite,
                    "status": "ok",
                    "article_title": hit.article_title,
                    "title_verified": check_title,
                    "body_excerpt": _strip_meta(hit.body[:250].replace("\n", " "))[:150],
                })
        else:
            results.append({
                "citation": f"{matched_src} {art}",
                "raw_match": full_cite,
                "status": "not_found",
                "message": f"{matched_src}에 {art} 없음 "
                           f"(실재: {_article_range_for(matched_src, articles)})",
            })
    return results
```

`main()`에 verify 서브커맨드 추가:
```python
def cmd_verify(args: argparse.Namespace) -> None:
    for r in verify_citation(args.text):
        print(f"[{r['status']}] {r['citation']}" +
              (f" — {r.get('message', '')}" if r.get("message") else ""))
```
```python
    pv = sub.add_parser("verify", help="조문 인용 실재성 검증")
    pv.add_argument("text")
    pv.set_defaults(func=cmd_verify)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_verify.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add law_search.py tests/test_verify.py
git commit -m "feat: verify_citation — 실재성 + 제목 환각(content_mismatch) 검증"
```

---

### Task 9: 상호참조 그래프 (`find_references`)

**Files:**
- Modify: `law_search.py`
- Test: `tests/test_refs.py`

**Interfaces:**
- Consumes: `load_index`, `_parse_article_token`, `_source_selector`, `_strip_meta`, `_nfc`
- Produces: `law_search.find_references(source, article, limit=20, include_mermaid=False) -> dict` — 키: `target{source,article,article_title,citation}`, `outgoing[]`, `incoming[]`, `counts{}`, (옵션)`mermaid`. 각 ref의 `scope`: `same_law` / `cross_law` / `external`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_refs.py`:
```python
import law_search as ls


def test_refs_outgoing_same_and_external(index):
    r = ls.find_references("테스트창업법", "제2조의2")
    assert r["target"]["citation"] == "테스트창업법 제2조의2"
    scopes = {(o["scope"], o["citation"]) for o in r["outgoing"]}
    assert ("same_law", "테스트창업법 제2조") in scopes
    assert ("external", "조세특례제한법 제6조") in scopes


def test_refs_incoming_cross_law(index):
    r = ls.find_references("테스트창업법", "제2조")
    incoming = {(i["scope"], i["citation"]) for i in r["incoming"]}
    assert ("cross_law", "테스트창업법 시행령 제3조") in incoming
    assert ("same_law", "테스트창업법 제2조의2") in incoming


def test_refs_invalid_target(index):
    r = ls.find_references("테스트창업법", "제99조")
    assert "error" in r


def test_refs_mermaid(index):
    r = ls.find_references("테스트창업법", "제2조", include_mermaid=True)
    assert r["mermaid"].startswith("flowchart LR")
    assert "테스트창업법 제2조" in r["mermaid"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_refs.py -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: 구현** — `law_search.py`의 `verify_citation` 아래에 추가:

```python
_SAME_LAW_CITE_RE = re.compile(r"(?<![가-힣A-Za-z0-9_])제(\d+)조(?:의(\d+))?")
_EXTERNAL_CITE_RE = re.compile(
    r"(?:「([^」\n]{2,40}?)」"
    r"|((?:[가-힣]+\s?){1,6}?(?:법률|시행령|시행규칙|법|규칙|령)))"
    r"\s*제(\d+)조(?:의(\d+))?")


def _around(body: str, pos: int, span: int = 60) -> str:
    start = max(0, pos - span)
    end = min(len(body), pos + span)
    s = _strip_meta(body[start:end].replace("\n", " "))
    return ("…" if start > 0 else "") + s + ("…" if end < len(body) else "")


def find_references(source: str, article: str, limit: int = 20,
                    include_mermaid: bool = False) -> dict:
    """대상 조문의 정방향(outgoing)·역방향(incoming) 인용 관계.

    scope: same_law(같은 법령 안) / cross_law(인덱스 내 다른 법령) /
    external(인덱스에 없는 법령).
    """
    parsed = _parse_article_token(article)
    if parsed is None:
        return {"error": f"조문 토큰 해석 불가: {article!r}"}
    no, sub = parsed
    articles = load_index()
    src_ok = _source_selector(source, articles)
    targets = [a for a in articles
               if src_ok(a.source) and a.article_no == no and a.article_sub == sub]
    if not targets:
        return {"error": f"대상 조문 없음: {source} 제{no}조" + (f"의{sub}" if sub else "")}
    targets.sort(key=lambda a: a.is_supplementary)  # 본칙 우선
    target = targets[0]
    known_sources = sorted({a.source for a in articles}, key=len, reverse=True)

    # ===== OUTGOING =====
    outgoing: list[dict] = []
    seen: set[tuple] = set()
    consumed: list[tuple[int, int]] = []
    for m in _EXTERNAL_CITE_RE.finditer(target.body):
        cited_name = re.sub(r"\s+", "", (m.group(1) or m.group(2) or ""))
        c_no, c_sub = int(m.group(3)), int(m.group(4) or 0)
        key = (cited_name, c_no, c_sub)
        if key in seen:
            continue
        seen.add(key)
        consumed.append((m.start(), m.end()))
        matched = next((s for s in known_sources
                        if cited_name in s.replace(" ", "") or s.replace(" ", "") in cited_name),
                       None)
        if matched:
            cited = next((a for a in articles
                          if a.source == matched and a.article_no == c_no
                          and a.article_sub == c_sub and not a.is_supplementary), None)
            if cited:
                scope = "same_law" if matched == target.source else "cross_law"
                outgoing.append({
                    "scope": scope,
                    "citation": cited.citation,
                    "article_title": cited.article_title,
                    "snippet": _strip_meta(cited.body[:200].replace("\n", " "))[:120],
                })
                continue
        outgoing.append({
            "scope": "external",
            "citation": f"{cited_name} 제{c_no}조" + (f"의{c_sub}" if c_sub else ""),
            "note": "인덱스에 없는 외부 법령 또는 조문 매칭 실패",
        })
    for m in _SAME_LAW_CITE_RE.finditer(target.body):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        c_no, c_sub = int(m.group(1)), int(m.group(2) or 0)
        if (c_no, c_sub) == (no, sub):
            continue
        key = (target.source, c_no, c_sub)
        if key in seen:
            continue
        seen.add(key)
        cited = next((a for a in articles
                      if a.source == target.source and a.article_no == c_no
                      and a.article_sub == c_sub and not a.is_supplementary), None)
        if cited:
            outgoing.append({
                "scope": "same_law",
                "citation": cited.citation,
                "article_title": cited.article_title,
                "snippet": _strip_meta(cited.body[:200].replace("\n", " "))[:120],
            })

    # ===== INCOMING =====
    incoming: list[dict] = []
    for a in articles:
        if a is target or a.is_supplementary:
            continue
        if a.source == target.source:
            for m in _SAME_LAW_CITE_RE.finditer(a.body):
                if int(m.group(1)) == no and int(m.group(2) or 0) == sub:
                    incoming.append({
                        "scope": "same_law",
                        "citation": a.citation,
                        "article_title": a.article_title,
                        "snippet": _around(a.body, m.start()),
                    })
                    break
        else:
            if target.source not in a.body:
                continue
            pos = 0
            while True:
                idx = a.body.find(target.source, pos)
                if idx < 0:
                    break
                after = a.body[idx + len(target.source): idx + len(target.source) + 60]
                m = re.match(r"\s*제(\d+)조(?:의(\d+))?", after)
                if m and int(m.group(1)) == no and int(m.group(2) or 0) == sub:
                    incoming.append({
                        "scope": "cross_law",
                        "citation": a.citation,
                        "article_title": a.article_title,
                        "snippet": _around(a.body, idx),
                    })
                    break
                pos = idx + len(target.source)

    result = {
        "target": {
            "source": target.source,
            "article": target.article,
            "article_title": target.article_title,
            "citation": target.citation,
        },
        "outgoing": outgoing[:limit],
        "incoming": incoming[:limit],
        "counts": {"outgoing": len(outgoing), "incoming": len(incoming)},
    }
    if include_mermaid:
        result["mermaid"] = _mermaid_graph(result)
    return result


def _mermaid_graph(result: dict) -> str:
    """incoming → target → outgoing flowchart."""
    lines = ["flowchart LR"]
    tid = "T"
    t = result["target"]
    lines.append(f'    {tid}["{t["citation"]}({t["article_title"]})"]')
    for i, ref in enumerate(result["incoming"]):
        lines.append(f'    I{i}["{ref["citation"]}"] --> {tid}')
    for i, ref in enumerate(result["outgoing"]):
        lines.append(f'    {tid} --> O{i}["{ref["citation"]}"]')
    return "\n".join(lines)
```

`main()`에 refs 서브커맨드 추가:
```python
def cmd_refs(args: argparse.Namespace) -> None:
    r = find_references(args.source, args.article)
    print(json.dumps(r, ensure_ascii=False, indent=1))
```
```python
    pr = sub.add_parser("refs", help="조문 상호참조")
    pr.add_argument("source")
    pr.add_argument("article")
    pr.set_defaults(func=cmd_refs)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -v`
Expected: 전체 통과 (41개)

- [ ] **Step 5: Commit**

```bash
git add law_search.py tests/test_refs.py
git commit -m "feat: find_references — 조문 인용 그래프 (same_law/cross_law/external) + mermaid"
```

---

### Task 10: MCP 서버 (`server.py`)

**Files:**
- Create: `server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `law_search.search / get_article / list_laws / verify_citation / find_references`
- Produces: `server.register_tools(mcp: FastMCP) -> None` (v2 원격 엔트리포인트가 재사용할 단일 등록 지점), `server.mcp` (FastMCP 인스턴스, stdio 실행)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py`:
```python
import asyncio


def test_five_tools_registered():
    import server
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws",
                     "verify_citation", "find_references"}


def test_instructions_mention_domain():
    import server
    assert "창업" in server.SERVER_INSTRUCTIONS
    assert "search_law" in server.SERVER_INSTRUCTIONS
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: 구현**

`server.py`:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -v`
Expected: 전체 통과 (43개)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: FastMCP stdio 서버 — 기본 5도구 + SERVER_INSTRUCTIONS"
```

---

### Task 11: 실데이터 동기화 + E2E 검증 + README

**Files:**
- Modify: `data/laws.json` (법령명 보정), `data/sources.json`·`data/laws/*.md` (동기화 산출물)
- Create: `README.md`

**Interfaces:**
- Consumes: 전체 파이프라인. **환경변수 `LAW_OC` 필요 — 사용자가 open.law.go.kr에서 발급.**

- [ ] **Step 1: API 구조 검증 (probe)**

```bash
python law_sync.py probe --query "중소기업창업 지원법" --full
```
Expected: 목록 JSON 출력 + `data/_cache/probe_*.json` 저장.
**저장된 본문 JSON을 열어 fixture(`sample_law.json`)와 필드명·구조를 대조한다.** 다르면 (예: `법령명_한글` vs `법령명한글`, 항이 dict 단건) `law_to_markdown`과 fixture를 실제 구조에 맞춰 수정하고 테스트 재실행. 이 단계가 이 태스크의 핵심 리스크 컨트롤이다.

- [ ] **Step 2: 법령명 보정**

각 큐레이션 항목에 대해 `python law_sync.py probe --query "{이름}"`으로 정확한 현행 법령명을 확인하고 `data/laws.json`을 보정한다 (예: "벤처기업육성에 관한 특별법"의 현행 정식 명칭 확인). 커밋:
```bash
git add data/laws.json
git commit -m "chore: 큐레이션 법령명 API 대조 보정"
```

- [ ] **Step 3: 전체 동기화 + 빌드**

```bash
python law_sync.py sync
python law_search.py build
```
Expected: `data/laws/`에 40~60개 md, `sources.json` errors 0건(있으면 개별 원인 확인), 인덱스 빌드 성공. 조문 수가 수천 단위인지 확인 (상법 하나만 900+조).

- [ ] **Step 4: CLI 스모크 테스트**

```bash
python law_search.py search "창업 세액감면"
python law_search.py get 조세특례제한법 제6조
python law_search.py verify "조세특례제한법 제6조에 따라 창업중소기업은 세액감면을 받는다"
python law_search.py refs "중소기업창업 지원법" 제2조
```
Expected: 각각 유의미한 결과. `get 조세특례제한법 제6조`는 "창업중소기업 등에 대한 세액감면" 조문이 나와야 한다. 이상하면 파서·검색을 디버깅.

- [ ] **Step 5: 데이터 커밋**

```bash
git add data/laws data/sources.json
git commit -m "data: 창업 법령 초기 동기화 (law.go.kr Open API)"
```

- [ ] **Step 6: Claude Desktop E2E**

`%APPDATA%\Claude\claude_desktop_config.json`에 서버 등록 (server.py docstring 참고) 후 Claude Desktop 완전 재시작. 자연어 시나리오 5개 확인:
1. "창업기업 세액감면 요건 알려줘" → search_law + get_article 호출, 조세특례제한법 제6조 근거 답변
2. "벤처기업 확인 요건이 뭐야" → 벤처기업법 관련 조문
3. "직원 첫 채용 때 근로계약서에 뭘 써야 해" → 근로기준법 제17조
4. "이 문서에 인용된 조문들 실재하는지 검증해줘: …" → verify_citation
5. "중소기업창업 지원법 제2조를 인용한 다른 조문 찾아줘" → find_references

- [ ] **Step 7: README 작성**

koica-reg-mcp README 구조를 따라 작성: 한 줄 소개 → 무엇을 해결하나 → 인덱싱 범위(법령 표) → 빠른 시작(설치·빌드·Claude Desktop 연결) → 사용 예시 → 도구 5개 표 → 데이터 구조 → 현행성 유지(law_sync 사용법) → 기술 메모 → 로드맵(v1.1 특화 3도구, v1.2 Actions 동기화, v2.0 원격 배포) → 라이선스(코드 MIT / 법령 데이터는 저작권법 제24조의2 공공저작물 + "법적 효력본은 law.go.kr 확인" 면책).

```bash
git add README.md
git commit -m "docs: README — 소개·설치·도구·로드맵·라이선스"
```

- [ ] **Step 8: 전체 테스트 최종 확인**

Run: `python -m pytest tests/ -v`
Expected: 전체 통과.

---

## v1.1 이후 (이 계획의 범위 밖 — 별도 계획으로)

스펙의 창업 특화 3도구(`delegation_map`, `startup_stage_guide`, `check_effective_date`)와 GitHub Actions 동기화(v1.2), 원격 배포(v2.0)는 v1.0 완성 후 별도 구현 계획을 작성한다. `data/stages.json` 큐레이션은 v1.0 데이터가 실제로 인덱싱된 뒤에야 조문 참조를 확정할 수 있다.
