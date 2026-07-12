# startup-law-mcp v1.2 안정화 패치 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 데이터 파괴 경로 차단(스냅샷 방어·원자 교체), MCP 입력 경계 검증, 데이터 정확성 결함 수정(URL·범위·인용 귀속·신선도), `data_status` 도구(10번째), README·CI 정비.

**Architecture:** 기존 4-파일 구조 유지(모듈 분리 없음 — 타당성분석 §2 P2 보류 결정). 각 결함은 실패하는 회귀 테스트로 먼저 재현 후 최소 수정. 기능 수정과 구조 변경을 같은 커밋에 섞지 않는다.

**Tech Stack:** 기존과 동일 (Python 3.10+, 표준 라이브러리, mcp). 신규 의존성 없음.

**스펙:** [docs/2026-07-12-보완리포트-타당성분석.md](../../2026-07-12-보완리포트-타당성분석.md) §5 채택안 (원 요구: [docs/2026-07-12-보완-고도화-리포트.md](../../2026-07-12-보완-고도화-리포트.md) — 단, 타당성분석에서 축소·보류된 항목은 그 판정을 따른다)

## Global Constraints

- **기존 정상 데이터를 절대 손상시키지 않는다** — 검증 실패 시 기존 스냅샷·파일 무변경이 모든 방어 로직의 완료 조건.
- 급감 기준: 명명된 정책 상수 `DRASTIC_DROP_RATIO = 0.7` (기존 대비 70% 초과 감소 시 거부).
- MCP 입력: `limit`은 1~50 정수, 문자열 인자는 비어 있지 않아야 함, `status`는 open/closing_soon/upcoming/closed만. 위반 시 `{"status": "invalid_input", "field": ..., "message": ...}` 반환 (빈 배열과 구분).
- 엔진 내부(law_search.search·programs.search_programs·list_open_programs·find_references)는 `limit = max(1, min(limit, 50))` clamp로 불변조건 유지.
- verify_citation 상태 집합: ok / content_mismatch / not_found / unknown_source / **ambiguous_source**(신규). 법령명이 인용에 직접 붙지 않은(간격 3자 이상) 경우 결과에 `"source_inference": "inferred"` 필드 추가.
- URL: `http(s)` 외 스킴 거부(빈 문자열), 스킴 없으면 `https://` 부여, `/` 시작 상대경로는 `https://www.k-startup.go.kr` 결합. 정규화 책임은 저장 경계(normalize_*) 한 곳.
- 보류 항목 구현 금지 (스코프 가드): snapshot_id 체계, staging 디렉터리·sha256, pyproject/lock/mypy/린트, 모듈 분리, BM25·역색인. 리뷰어는 이들이 diff에 나타나면 Extra로 판정.
- 표준 라이브러리만. UTF-8 명시. NFC(law_search._nfc) 재사용. conventional commits. `python -m pytest` (Windows).
- API 키는 환경변수로만 — LAW_OC 이메일 아이디·DATA_GO_KR_KEY 64자 hex 문자열이 어떤 추적 파일에도(이 계획 문서 포함) 리터럴로 없어야 함.
- 전체 스위트 기준선 77개 — 항상 전부 통과 유지. (아래 태스크별 누계는 참고치이며 파일별 covering 수가 우선.)

---

### Task 1: 지원사업 sync 방어 (스키마 검증·0건·급감·원자 교체)

**Files:**
- Modify: `program_sync.py`
- Test: `tests/test_program_sync.py` (기존 1개 테스트 수정 + 7개 추가)

**Interfaces:**
- Consumes: `_get_json`, `fetch_current_announcements`, `fetch_all`, `normalize_*`, `PROGRAMS_DIR`
- Produces:
  - `program_sync.SyncValidationError(RuntimeError)` — 안전 기준 미달, 기존 스냅샷 보존
  - `program_sync.DRASTIC_DROP_RATIO = 0.7`
  - `fetch_page`가 엔벨로프 검증 수행 (최상위 dict / data 배열 / totalCount 정수)
  - `sync(key) -> dict` 반환 형태 변경: `{"status": "ok", "fetched_at": ISO, "announcements": {"before": int|None, "after": int, "delta": int}, "intros": {동일}}` — **Task 6·7과 server.sync_programs가 이 형태에 의존**

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_program_sync.py`에 반영:

① 기존 `test_sync_writes_snapshots`의 결과 단언 2줄을 다음으로 교체:
```python
    assert result["status"] == "ok"
    assert result["announcements"]["after"] == 2
    assert result["intros"]["after"] == 1
```

② 파일 끝에 추가:
```python
def test_envelope_rejects_non_object(monkeypatch):
    monkeypatch.setattr(program_sync, "_get_json", lambda url: ["not", "an", "object"])
    with pytest.raises(program_sync.SyncValidationError, match="객체가 아님"):
        program_sync.fetch_page("k", "announcement")


def test_envelope_rejects_non_list_data(monkeypatch):
    monkeypatch.setattr(program_sync, "_get_json",
                        lambda url: {"totalCount": 1, "data": "oops"})
    with pytest.raises(program_sync.SyncValidationError, match="배열이 아님"):
        program_sync.fetch_page("k", "announcement")


def test_envelope_rejects_bad_total_count(monkeypatch):
    monkeypatch.setattr(program_sync, "_get_json",
                        lambda url: {"totalCount": "abc", "data": []})
    with pytest.raises(program_sync.SyncValidationError, match="totalCount"):
        program_sync.fetch_page("k", "announcement")


def test_sync_rejects_empty_success_response(env, monkeypatch):
    program_sync.sync("k")  # 정상 스냅샷(공고2·소개1) 생성
    before = (env / "programs" / "announcements.json").read_text(encoding="utf-8")
    monkeypatch.setattr(program_sync, "fetch_page",
                        lambda key, target, page=1, per_page=100: {"totalCount": 0, "data": []})
    with pytest.raises(program_sync.SyncValidationError, match="0건"):
        program_sync.sync("k")
    assert (env / "programs" / "announcements.json").read_text(encoding="utf-8") == before


def test_sync_rejects_drastic_drop(env):
    # 기존 10건 스냅샷 심기 — env fake는 공고 2건 반환 → 10→2는 70% 초과 감소
    d = env / "programs"
    d.mkdir(exist_ok=True)
    items = [{"id": str(i), "kind": "공고", "name": f"공고{i}"} for i in range(10)]
    (d / "announcements.json").write_text(json.dumps(
        {"fetched_at": "2026-07-10T00:00:00+00:00", "count": 10, "items": items},
        ensure_ascii=False), encoding="utf-8")
    with pytest.raises(program_sync.SyncValidationError, match="급감"):
        program_sync.sync("k")
    kept = json.loads((d / "announcements.json").read_text(encoding="utf-8"))
    assert kept["count"] == 10


def test_sync_rejects_schema_drift(env, monkeypatch):
    program_sync.sync("k")
    before = (env / "programs" / "announcements.json").read_text(encoding="utf-8")

    def drifted(key, target, page=1, per_page=100):
        if page == 1:
            return {"totalCount": 2, "data": [
                {"rcrt_prgs_yn": "Y", "totally_new_field": "x"},
                {"rcrt_prgs_yn": "Y", "totally_new_field": "y"}]}
        return {"totalCount": 2, "data": []}

    monkeypatch.setattr(program_sync, "fetch_page", drifted)
    with pytest.raises(program_sync.SyncValidationError, match="필수 필드"):
        program_sync.sync("k")
    assert (env / "programs" / "announcements.json").read_text(encoding="utf-8") == before


def test_sync_reports_before_after(env):
    r1 = program_sync.sync("k")
    assert r1["announcements"] == {"before": None, "after": 2, "delta": 2}
    r2 = program_sync.sync("k")
    assert r2["announcements"] == {"before": 2, "after": 2, "delta": 0}


def test_sync_atomic_replace_no_tmp_leftover(env):
    program_sync.sync("k")
    assert not list((env / "programs").glob("*.tmp"))
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_program_sync.py -v`
Expected: 신규 8개 FAIL (`AttributeError: ... SyncValidationError` 등), 기존 수정분 FAIL

- [ ] **Step 3: 구현** — `program_sync.py`:

① `_get_json` 아래에 추가:
```python
DRASTIC_DROP_RATIO = 0.7  # 기존 건수 대비 이 비율 초과 감소 시 동기화 거부 (정책값)


class SyncValidationError(RuntimeError):
    """응답·결과가 안전 기준 미달 — 기존 스냅샷을 보존하고 중단."""


def _validate_envelope(data, target: str) -> None:
    """응답 엔벨로프 스키마 검증 (probe 확정: totalCount/data[])."""
    if not isinstance(data, dict):
        raise SyncValidationError(f"{target}: 응답 최상위가 객체가 아님 ({type(data).__name__})")
    if not isinstance(data.get("data"), list):
        raise SyncValidationError(f"{target}: 'data'가 배열이 아님")
    tc = data.get("totalCount")
    ok = (isinstance(tc, int) and not isinstance(tc, bool) and tc >= 0) or \
         (isinstance(tc, str) and tc.isdigit())
    if not ok:
        raise SyncValidationError(f"{target}: 'totalCount'가 0 이상 정수가 아님 ({tc!r})")
```

② `fetch_page`를 다음으로 교체:
```python
def fetch_page(key: str, target: str, page: int = 1, per_page: int = 100) -> dict:
    """한 페이지 조회 + 엔벨로프 검증."""
    qs = urllib.parse.urlencode({
        "serviceKey": key, "page": page, "perPage": per_page, "returnType": "json",
    })
    data = _get_json(f"{API_BASE}/{ENDPOINTS[target]}?{qs}")
    _validate_envelope(data, target)
    return data
```

③ `sync`를 다음으로 교체하고 그 위에 헬퍼 3개 추가:
```python
def _snapshot_count(fname: str) -> int | None:
    p = PROGRAMS_DIR / fname
    if not p.exists():
        return None
    try:
        return len(json.loads(p.read_text(encoding="utf-8")).get("items", []))
    except (json.JSONDecodeError, OSError):
        return None


def _guard_required_fields(label: str, items: list[dict], require_id: bool) -> None:
    """정규화 결과의 필수 필드 누락률이 10%를 넘으면 스키마 변경으로 간주."""
    if not items:
        return
    missing = sum(1 for it in items
                  if not it.get("name") or (require_id and not it.get("id")))
    if missing / len(items) > 0.10:
        raise SyncValidationError(
            f"{label}: 필수 필드 누락 {missing}/{len(items)}건 — API 스키마 변경 의심, 중단")


def _guard_counts(label: str, before: int | None, after: int) -> None:
    if after == 0 and (before or 0) > 0:
        raise SyncValidationError(f"{label}: 신규 0건 — 기존 {before}건 보존을 위해 중단")
    if before and after < before * (1 - DRASTIC_DROP_RATIO):
        raise SyncValidationError(
            f"{label}: 급감 감지 ({before} → {after}건) — 기준 "
            f"{int(DRASTIC_DROP_RATIO * 100)}% 초과 감소, 중단")


def _write_snapshot(fname: str, payload: dict) -> None:
    """임시 파일 기록 → JSON 재파싱 검증 → 원자 교체(os.replace)."""
    PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROGRAMS_DIR / (fname + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, PROGRAMS_DIR / fname)


def sync(key: str) -> dict:
    """현행 공고 + 사업소개 수집 → 안전 검증 통과 시에만 스냅샷 교체."""
    from datetime import datetime, timezone

    ann_raw = fetch_current_announcements(key)
    intro_raw = fetch_all(key, "intro")
    ann = [normalize_announcement(r) for r in ann_raw]
    intros = [normalize_intro(r) for r in intro_raw]

    if not ann and not intros:
        raise SyncValidationError("공고·사업소개 모두 0건 — 비정상 응답 의심, 중단")
    before_ann = _snapshot_count("announcements.json")
    before_intro = _snapshot_count("intros.json")
    _guard_required_fields("공고", ann, require_id=True)
    _guard_required_fields("사업소개", intros, require_id=False)
    _guard_counts("공고", before_ann, len(ann))
    _guard_counts("사업소개", before_intro, len(intros))

    fetched_at = datetime.now(timezone.utc).isoformat()
    for fname, items in (("announcements.json", ann), ("intros.json", intros)):
        _write_snapshot(fname, {"fetched_at": fetched_at, "count": len(items), "items": items})
    result = {
        "status": "ok",
        "fetched_at": fetched_at,
        "announcements": {"before": before_ann, "after": len(ann),
                          "delta": len(ann) - (before_ann or 0)},
        "intros": {"before": before_intro, "after": len(intros),
                   "delta": len(intros) - (before_intro or 0)},
    }
    print(f"동기화 완료: 공고 {len(ann)}건({result['announcements']['delta']:+d}), "
          f"사업소개 {len(intros)}건({result['intros']['delta']:+d})")
    return result
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_program_sync.py -v` → 14 passed. 전체: 85 passed.

- [ ] **Step 5: Commit**

```bash
git add program_sync.py tests/test_program_sync.py
git commit -m "fix: sync 안전 방어 — 스키마 검증·0건·급감(70%)·원자 교체·before/after"
```

---

### Task 2: URL 정규화 (저장 경계)

**Files:**
- Modify: `program_sync.py` (`_normalize_url` 추가, `normalize_announcement`/`normalize_intro`의 url 줄 수정)
- Test: `tests/test_program_sync_utils.py`, `tests/test_program_normalize.py`

**Interfaces:**
- Produces: `program_sync._normalize_url(u) -> str`, `KSTARTUP_BASE = "https://www.k-startup.go.kr"`. 기존 커밋 스냅샷 511건의 보정은 **Task 7의 실데이터 재동기화**로 해결 (저장 경계 단일 책임 유지).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_program_sync_utils.py` 끝에:
```python
def test_normalize_url_variants():
    f = program_sync._normalize_url
    assert f("www.k-startup.go.kr/a?b=1") == "https://www.k-startup.go.kr/a?b=1"
    assert f("/web/contents/x.do") == "https://www.k-startup.go.kr/web/contents/x.do"
    assert f("https://already.example/x") == "https://already.example/x"
    assert f("http://legacy.example/x") == "http://legacy.example/x"
    assert f("ftp://bad.example/x") == ""
    assert f("javascript:alert(1)") == ""
    assert f(None) == ""
```

`tests/test_program_normalize.py` 끝에:
```python
def test_normalize_intro_url_gets_scheme():
    recs = [program_sync.normalize_intro(r) for r in _fx()["intro_items"]]
    for r in recs:
        assert r["url"] == "" or r["url"].startswith(("https://", "http://"))
    assert any(r["url"].startswith("https://") for r in recs)  # 실 fixture는 www. 시작
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_program_sync_utils.py tests/test_program_normalize.py -v`
Expected: 신규 2개 FAIL (`AttributeError: _normalize_url` / url 스킴 단언 실패)

- [ ] **Step 3: 구현** — `program_sync.py`의 `_date_norm` 아래에 추가:

```python
KSTARTUP_BASE = "https://www.k-startup.go.kr"


def _normalize_url(u) -> str:
    """스킴 없는 K-Startup URL 보정. http(s) 외 스킴은 거부(빈 문자열)."""
    u = _s(u)
    if not u:
        return ""
    if u.startswith(("http://", "https://")):
        return u
    if "://" in u or u.lower().startswith(("javascript:", "data:", "mailto:")):
        return ""
    if u.startswith("/"):
        return KSTARTUP_BASE + u
    return "https://" + u
```

그리고 두 정규화 함수의 url 줄을 교체:
- `normalize_announcement`: `"url": _normalize_url(raw.get("detl_pg_url") or raw.get("biz_gdnc_url")),`
- `normalize_intro`: `"url": _normalize_url(raw.get("detl_pg_url")),`

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q` → 87 passed (기존 normalize 테스트는 url 값을 단언하지 않아 안전)

- [ ] **Step 5: Commit**

```bash
git add program_sync.py tests/test_program_sync_utils.py tests/test_program_normalize.py
git commit -m "fix: URL 저장 경계 정규화 — https 부여·비허용 스킴 거부"
```

---

### Task 3: 법령 매니페스트 기반 인덱싱 + stale 보존 + 고아 정리 + 캐시 갱신

**Files:**
- Modify: `law_search.py` (`build_index` 교체 + `_manifest_files` 추가), `law_sync.py` (`sync` 교체)
- Test: `tests/test_sync.py`, `tests/test_parse.py`

**Interfaces:**
- Produces:
  - `law_search._manifest_files() -> Optional[set[str]]` — sources.json 등재 파일명 (없으면 None → 전체 인덱싱 폴백, 테스트 픽스처 호환)
  - `build_index()`가 매니페스트 파일만 인덱싱 + 완료 시 `_INDEX_CACHE` 즉시 갱신
  - `law_sync.sync()`: 이번 실행에서 갱신 실패한 법령은 이전 매니페스트 엔트리를 `"stale": true, "stale_reason": ...`로 유지(검색 유지·오류 격리 정책), 큐레이션에서 빠진 법령의 md는 삭제(prune). Task 6 `data_status`가 stale 필드를 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_sync.py` 끝에:
```python
def test_sync_prunes_removed_curation(env):
    law_sync.sync("dummy-oc")
    assert (env / "laws" / "법률_테스트창업법.md").exists()
    # 큐레이션에서 테스트창업법 제거 후 재동기화 → 파일·매니페스트에서 제외
    (env / "laws.json").write_text(json.dumps(
        {"laws": [{"name": "존재하지않는법", "group": "테스트"}]}, ensure_ascii=False),
        encoding="utf-8")
    result = law_sync.sync("dummy-oc")
    assert not (env / "laws" / "법률_테스트창업법.md").exists()
    assert "테스트창업법" not in {s["name"] for s in result["sources"]}


def test_sync_carries_stale_on_failure(env, monkeypatch):
    law_sync.sync("dummy-oc")  # 정상 세대 확보

    def boom(oc, query):
        raise RuntimeError("api down")

    monkeypatch.setattr(law_sync, "fetch_law_list", boom)
    result = law_sync.sync("dummy-oc")
    by_name = {s["name"]: s for s in result["sources"]}
    assert by_name["테스트창업법"].get("stale") is True
    assert "api down" in by_name["테스트창업법"].get("stale_reason", "")
    assert (env / "laws" / "법률_테스트창업법.md").exists()  # prune에서 보호
```

`tests/test_parse.py` 끝에 (파일 상단에 `import json` 추가):
```python
def test_build_index_uses_manifest_only(tmp_path, monkeypatch):
    laws = tmp_path / "laws"
    laws.mkdir()
    src_md = (FIXTURES / "법률_테스트창업법.md").read_text(encoding="utf-8")
    (laws / "법률_테스트창업법.md").write_text(src_md, encoding="utf-8")
    (laws / "법률_고아법.md").write_text(src_md.replace("테스트창업법", "고아법"),
                                          encoding="utf-8")
    (tmp_path / "sources.json").write_text(json.dumps(
        {"count": 1, "sources": [{"name": "테스트창업법", "file": "법률_테스트창업법.md"}]},
        ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ls, "DATA", tmp_path)
    monkeypatch.setattr(ls, "LAWS_DIR", laws)
    monkeypatch.setattr(ls, "INDEX_FILE", tmp_path / "index.json")
    monkeypatch.setattr(ls, "_INDEX_CACHE", None)
    arts = ls.build_index()
    assert {a.source for a in arts} == {"테스트창업법"}  # 고아법 제외
    assert ls.load_index() is arts  # 빌드 직후 캐시가 같은 세대
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_sync.py tests/test_parse.py -v`
Expected: 신규 3개 FAIL (prune 미구현·stale 미구현·고아법 인덱싱됨)

- [ ] **Step 3: 구현**

① `law_search.py` — `build_index` 위에 추가 후 `build_index` 교체:
```python
def _manifest_files() -> Optional[set[str]]:
    """sources.json 등재 파일명 집합. 매니페스트가 없으면 None(전체 인덱싱 폴백)."""
    src = DATA / "sources.json"
    if not src.exists():
        return None
    try:
        manifest = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    files = {s.get("file") for s in manifest.get("sources", []) if s.get("file")}
    return files or None


def build_index() -> list[Article]:
    global _INDEX_CACHE
    allowed = _manifest_files()
    arts: list[Article] = []
    skipped: list[str] = []
    for p in sorted(LAWS_DIR.glob("*.md")):
        if allowed is not None and p.name not in allowed:
            skipped.append(p.name)
            continue
        arts.extend(parse_md(p))
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps([asdict(a) for a in arts], ensure_ascii=False),
        encoding="utf-8")
    _INDEX_CACHE = arts  # 재빌드 즉시 캐시 갱신 — stale 캐시 방지
    msg = f"인덱스 빌드 완료: 문서 {len({a.source for a in arts})}개, 조문 {len(arts)}개"
    if skipped:
        msg += f" (매니페스트 외 {len(skipped)}개 제외)"
    print(msg)
    return arts
```

② `law_sync.py` — `sync`를 다음으로 교체 (오류 격리·`--only` 동작은 기존 유지, stale 보존과 prune 추가):
```python
def sync(oc: str, only: str | None = None) -> dict:
    """laws.json 큐레이션 목록 전체를 동기화. 법령 단위 오류 격리.

    갱신 실패 법령은 이전 매니페스트 엔트리를 stale로 유지해 검색에서 사라지지
    않게 하고, 큐레이션에서 제거된 법령의 md는 삭제(prune)한다.
    """
    curation = json.loads((DATA / "laws.json").read_text(encoding="utf-8"))
    LAWS_DIR.mkdir(parents=True, exist_ok=True)

    prev_by_name: dict[str, dict] = {}
    src_file = DATA / "sources.json"
    if src_file.exists():
        try:
            prev_by_name = {s.get("name"): s for s in
                            json.loads(src_file.read_text(encoding="utf-8")).get("sources", [])}
        except json.JSONDecodeError:
            prev_by_name = {}

    sources: list[dict] = []
    errors: list[dict] = []
    all_wanted: list[str] = []
    failed_reason: dict[str, str] = {}

    for entry in curation["laws"]:
        name = entry["name"]
        if only and only not in name:
            continue
        wanted = [name]
        if entry.get("include_subordinate", True):
            wanted += [f"{name} 시행령", f"{name} 시행규칙"]
        all_wanted.extend(wanted)
        try:
            hits = fetch_law_list(oc, name)
        except Exception as e:  # noqa: BLE001 — 법령 단위 격리
            errors.append({"law": name, "stage": "search", "error": str(e)})
            for w in wanted:
                failed_reason[w] = f"search: {e}"
            continue
        by_name = {str(h.get("법령명한글", "")).strip(): h for h in hits}
        for w in wanted:
            hit = by_name.get(w)
            if not hit:
                if w == name:
                    errors.append({"law": w, "stage": "match",
                                   "error": "법령 목록에서 정확일치 결과 없음"})
                    failed_reason[w] = "match: 목록에서 미발견"
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
                failed_reason[w] = f"fetch: {e}"

    # 갱신 실패분: 이전 세대 엔트리를 stale로 유지 (파일이 남아 있는 경우만)
    fetched_names = {s["name"] for s in sources}
    for w in all_wanted:
        if w in fetched_names or w not in failed_reason:
            continue
        p = prev_by_name.get(w)
        if p and (LAWS_DIR / p.get("file", "")).exists():
            stale = dict(p)
            stale["stale"] = True
            stale["stale_reason"] = failed_reason[w]
            sources.append(stale)

    manifest = {"count": len(sources), "sources": sources, "errors": errors}
    src_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    # 고아 파일 정리 — 새 매니페스트(stale 포함)에 없는 md 삭제
    valid_files = {s.get("file") for s in sources}
    removed = []
    for p in LAWS_DIR.glob("*.md"):
        if p.name not in valid_files:
            p.unlink()
            removed.append(p.name)
    if removed:
        print(f"고아 파일 {len(removed)}개 제거: {', '.join(removed[:5])}")
    print(f"동기화 완료: {len(sources)}개 문서(스테일 {sum(1 for s in sources if s.get('stale'))}건 포함), "
          f"오류 {len(errors)}건")
    return manifest
```

**주의(`--only` 상호작용):** `only` 필터로 스킵된 큐레이션 항목은 `all_wanted`에 들어가지 않아 stale 보존 대상이 아니고, prune에서 해당 파일이 삭제될 수 있다. 이를 막기 위해 prune은 `only`가 지정된 경우 건너뛴다 — 위 코드의 prune 블록을 `if only is None:`로 감싸라(들여쓰기 한 단계). 기존 `test_sync_only_filter`가 이 경로를 지킨다.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q` → 90 passed (기존 test_sync 5개·test_parse 7개 포함 전부)

- [ ] **Step 5: Commit**

```bash
git add law_search.py law_sync.py tests/test_sync.py tests/test_parse.py
git commit -m "fix: 매니페스트 기반 인덱싱 + 실패 법령 stale 보존 + 고아 정리 + 빌드 캐시 갱신"
```

---

### Task 4: MCP 입력 경계 검증 + 엔진 limit clamp

**Files:**
- Modify: `server.py` (검증 헬퍼 + 각 도구 가드), `law_search.py` (search·find_references clamp), `programs.py` (search_programs·list_open_programs clamp)
- Test: `tests/test_input_validation.py` (신규)

**Interfaces:**
- Produces: `server._invalid(field, message) -> dict`, `server._require_text(value, field)`, `server._check_limit(limit, lo=1, hi=50)`, `server._check_enum(value, field, allowed)`, `server._VALID_STATUS = ("open", "closing_soon", "upcoming", "closed")` — 모듈 레벨(직접 테스트 가능). 위반 시 `{"status": "invalid_input", "field", "message"}`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_input_validation.py`:

```python
import asyncio
from datetime import date

import law_search as ls
import programs
import server


def test_validators_boundaries():
    assert server._require_text("  ", "query")["status"] == "invalid_input"
    assert server._require_text(None, "query")["status"] == "invalid_input"
    assert server._require_text("창업", "query") is None
    for bad in (-1, 0, 51, True):
        assert server._check_limit(bad)["status"] == "invalid_input"
    for ok in (1, 50):
        assert server._check_limit(ok) is None
    assert server._check_enum("weird", "status", ("open", "closed"))["status"] == "invalid_input"
    assert server._check_enum(None, "status", ("open",)) is None


def test_engine_clamps_negative_limit(index):
    # clamp 전에는 scored[:-1]로 1건 결과가 0건이 됐다
    assert len(ls.search("정의", limit=-1)) == 1


def test_programs_clamps_negative_limit(programs_index):
    rows = programs.search_programs("창업", limit=-1, today=date(2026, 7, 11))["results"]
    assert len(rows) == 1  # clamp: -1 → 1


def test_registered_tool_rejects_blank_query():
    res = asyncio.run(server.mcp.call_tool("search_law", {"query": "   "}))
    assert "invalid_input" in str(res)


def test_registered_tool_rejects_bad_limit():
    res = asyncio.run(server.mcp.call_tool("search_program", {"query": "창업", "limit": -1}))
    assert "invalid_input" in str(res)


def test_registered_tool_rejects_bad_status():
    res = asyncio.run(server.mcp.call_tool("search_program", {"query": "창업", "status": "opened"}))
    assert "invalid_input" in str(res)
```

(참고: `mcp.call_tool`의 반환 래핑 형태는 mcp 버전에 따라 다르므로 `str(res)` 포함 단언으로 형태에 관대하게 검증한다. `call_tool`이 예외를 던지는 구현이면 BLOCKED로 보고하라 — 단언을 바꾸지 말 것.)

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_input_validation.py -v`
Expected: FAIL — `AttributeError: module 'server' has no attribute '_require_text'` 등

- [ ] **Step 3: 구현**

① `server.py` — `SERVER_INSTRUCTIONS` 아래·`register_tools` 위에 추가:
```python
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
```

② 각 도구 본문 첫 부분에 가드 삽입 (return 타입 힌트는 `-> dict`로 바꾸거나 `list[dict] | dict`로 확장):
- `search_law`: `err = _require_text(query, "query") or _check_limit(limit) or _check_enum(law_type, "law_type", _known_law_types());  if err: return err`
- `get_article`: `err = _require_text(source, "source") or _require_text(article, "article");  if err: return err`
- `list_laws`: `err = _check_enum(law_type, "law_type", _known_law_types());  if err: return err`
- `verify_citation`: `err = _require_text(text, "text");  if err: return err`
- `find_references`: `err = _require_text(source, "source") or _require_text(article, "article") or _check_limit(limit);  if err: return err`
- `search_program`: `err = _require_text(query, "query") or _check_limit(limit) or _check_enum(status, "status", _VALID_STATUS);  if err: return err`
- `get_program`: `err = _require_text(name, "name");  if err: return err`
- `list_open_programs`: `err = _check_limit(limit);  if err: return err`

③ 엔진 clamp — 각 함수 서두(인덱스 로드 직후)에 한 줄:
- `law_search.search`: `limit = max(1, min(limit, 50))`
- `law_search.find_references`: `limit = max(1, min(limit, 50))`
- `programs.search_programs`, `programs.list_open_programs`: `limit = max(1, min(limit, 50))`

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q` → 96 passed

- [ ] **Step 5: Commit**

```bash
git add server.py law_search.py programs.py tests/test_input_validation.py
git commit -m "fix: MCP 입력 경계 검증(invalid_input) + 엔진 limit clamp(1~50)"
```

---

### Task 5: 인용 정확성 — 범위 정확일치 + inferred/ambiguous 귀속

**Files:**
- Modify: `law_search.py` (`_article_range_for` 한 줄 수정, `verify_citation` 교체)
- Test: `tests/test_verify.py`

**Interfaces:**
- Produces: verify 결과에 신규 상태 `ambiguous_source`(`candidates` 목록 동봉)와 신규 필드 `source_inference: "inferred"`(법령명이 인용에 직접 붙지 않은 경우). **기존 11개 verify 테스트의 기대값은 전부 불변이어야 한다** (기존 픽스처는 모두 explicit 인용).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_verify.py` 끝에:

```python
def test_article_range_exact_source(index):
    # 시행령 조문(제2조·제3조)이 본법 범위에 혼입되면 4개가 된다
    rng = ls._article_range_for("테스트창업법", ls.load_index())
    assert "총 3개" in rng


def test_verify_inferred_source(index):
    r = ls.verify_citation("테스트창업법은 창업 지원의 근간이 되는 법률이다. 한편 여기서 제2조에 따르면")
    assert r[0]["status"] == "ok"
    assert r[0].get("source_inference") == "inferred"


def test_verify_explicit_has_no_inference_flag(index):
    r = ls.verify_citation("테스트창업법 제2조에 따라")
    assert r[0]["status"] == "ok"
    assert "source_inference" not in r[0]


def test_verify_ambiguous_source(index):
    text = "테스트창업법과 그 하위법령인 테스트창업법 시행령을 함께 검토한다. 이때 제2조는"
    r = ls.verify_citation(text)
    assert r[0]["status"] == "ambiguous_source"
    assert "테스트창업법" in r[0]["candidates"]
    assert "테스트창업법 시행령" in r[0]["candidates"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_verify.py -v`
Expected: 신규 4개 FAIL ("총 4개" 반환·inferred/ambiguous 미구현), 기존 11개 PASS 유지

- [ ] **Step 3: 구현** — `law_search.py`:

① `_article_range_for`의 필터 조건에서 `source_nfc in a.source`를 `a.source == source_nfc`로 교체 (나머지 동일).

② `verify_citation`을 다음으로 교체:
```python
def verify_citation(text: str) -> list[dict]:
    """텍스트 내 모든 '{법령명} 제N조[의M][(제목)]' 인용을 인덱스로 교차검증.

    status: ok / content_mismatch / not_found / unknown_source / ambiguous_source.
    법령명이 인용에 직접 붙지 않은 경우(간격 3자 이상) source_inference="inferred"를
    표기하고, 직전 문맥에 서로 다른 법령명이 복수면 ambiguous_source로 검증을 보류한다.
    """
    text_nfc = _nfc(text)
    articles = load_index()
    known_sources = sorted({a.source for a in articles}, key=len, reverse=True)

    def nearest_source(prefix: str):
        """(가장 가까운 법령명, 인용까지 간격, 문맥 내 후보 법령들)."""
        spans = []
        for src in known_sources:
            start = 0
            while True:
                pos = prefix.find(src, start)
                if pos < 0:
                    break
                spans.append((pos, pos + len(src), src))
                start = pos + 1
        # 다른 매칭 안에 완전히 포함된 이름(예: 시행령명 내부의 모법명)은 제외
        maximal = [s for s in spans
                   if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in spans)]
        if not maximal:
            return None, None, []
        best = max(maximal, key=lambda s: (s[0], s[1] - s[0]))
        gap = len(prefix) - best[1]
        return best[2], gap, sorted({s[2] for s in maximal})

    results = []
    for m in CITATION_RE.finditer(text_nfc):
        prefix = text_nfc[max(0, m.start() - 80): m.start()]
        matched_src, gap, candidates = nearest_source(prefix)
        art = f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "")
        full_cite = text_nfc[m.start(): m.end()]
        if not matched_src:
            results.append({
                "citation": full_cite,
                "status": "unknown_source",
                "message": "직전 텍스트에서 인덱싱된 법령명을 찾지 못함",
            })
            continue
        explicit = gap is not None and gap <= 2
        if not explicit and len(candidates) >= 2:
            results.append({
                "citation": full_cite,
                "status": "ambiguous_source",
                "candidates": candidates,
                "message": "직전 문맥에 복수의 법령명이 있고 인용에 법령명이 직접 붙어 "
                           "있지 않음 — 귀속 보류",
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
                res = {
                    "citation": f"{matched_src} {art}",
                    "raw_match": full_cite,
                    "status": "content_mismatch",
                    "cited_title": cited_title,
                    "actual_title": hit.article_title,
                    "message": f"{matched_src} {art}의 실제 제목은 '{hit.article_title}' — "
                               f"인용의 '{cited_title}'와 불일치 (내용 환각 가능)",
                }
            else:
                res = {
                    "citation": f"{matched_src} {art}",
                    "raw_match": full_cite,
                    "status": "ok",
                    "article_title": hit.article_title,
                    "title_verified": check_title,
                    "body_excerpt": _strip_meta(hit.body[:250].replace("\n", " "))[:150],
                }
        else:
            res = {
                "citation": f"{matched_src} {art}",
                "raw_match": full_cite,
                "status": "not_found",
                "message": f"{matched_src}에 {art} 없음 "
                           f"(실재: {_article_range_for(matched_src, articles)})",
            }
        if not explicit:
            res["source_inference"] = "inferred"
        results.append(res)
    return results
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_verify.py -v` → 15 passed. 전체: 100 passed.

- [ ] **Step 5: Commit**

```bash
git add law_search.py tests/test_verify.py
git commit -m "fix: 인용 귀속 신뢰도 — 범위 정확일치·inferred 표기·ambiguous_source 상태"
```

---

### Task 6: 신선도·정합성 경고 확장 + `data_status` 도구 (10번째)

**Files:**
- Modify: `programs.py` (`load_programs` 교체 + `data_warnings` 추가 + `staleness_warning` 래퍼화), `server.py` (`data_status` 도구 + `import json` + INSTRUCTIONS 한 줄)
- Test: `tests/test_programs.py`, `tests/test_server.py`

**Interfaces:**
- Produces:
  - `programs.data_warnings(data, today=None) -> list[str]` — invalid_timestamp / future_timestamp / stale / integrity 경고 목록
  - `load_programs()` 반환에 `"integrity_warnings": list[str]` 추가 (count_mismatch / snapshot_incomplete / fetched_at_mismatch)
  - `staleness_warning`은 `"; ".join(data_warnings(...)) or None` 래퍼 (기존 호출부 하위호환)
  - server `data_status() -> {"law": {...}, "programs": {...}}` — Task 3의 stale 필드를 노출. 도구 수 10.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_programs.py` 끝에 (파일 상단에 `import json` 추가):
```python
def test_invalid_fetched_at_warns():
    w = programs.staleness_warning({"fetched_at": "garbage"}, T)
    assert w is not None and "invalid_timestamp" in w


def test_future_fetched_at_warns():
    w = programs.staleness_warning({"fetched_at": "2027-01-01T00:00:00+00:00"}, T)
    assert w is not None and "future_timestamp" in w


def test_integrity_warnings_collected(monkeypatch, tmp_path):
    d = tmp_path / "programs"
    d.mkdir()
    (d / "announcements.json").write_text(json.dumps(
        {"fetched_at": "2026-07-10T00:00:00+00:00", "count": 5, "items": []}),
        encoding="utf-8")  # count 불일치 + intros 파일 없음
    monkeypatch.setattr(programs, "PROGRAMS_DIR", d)
    monkeypatch.setattr(programs, "_CACHE", None)
    joined = " ".join(programs.load_programs()["integrity_warnings"])
    assert "count_mismatch" in joined
    assert "snapshot_incomplete" in joined
```

`tests/test_server.py`의 `test_nine_tools_registered`를 다음으로 교체:
```python
def test_ten_tools_registered():
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws", "verify_citation",
                     "find_references", "search_program", "get_program",
                     "list_open_programs", "sync_programs", "data_status"}
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_programs.py tests/test_server.py -v`
Expected: 신규 3개 + 교체 1개 FAIL

- [ ] **Step 3: 구현**

① `programs.py` — `load_programs`를 다음으로 교체:
```python
def load_programs(use_cache: bool = True) -> dict:
    """{"announcements", "intros", "fetched_at", "integrity_warnings"}"""
    global _CACHE
    if use_cache and _CACHE is not None:
        return _CACHE
    out = {"announcements": [], "intros": [], "fetched_at": None,
           "integrity_warnings": []}
    metas: dict[str, Optional[str]] = {}
    for field, fname in (("announcements", "announcements.json"),
                         ("intros", "intros.json")):
        p = PROGRAMS_DIR / fname
        if not p.exists():
            metas[field] = None
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", [])
        out[field] = items
        declared = data.get("count")
        if isinstance(declared, int) and declared != len(items):
            out["integrity_warnings"].append(
                f"count_mismatch: {fname} count={declared}, 실제 {len(items)}건")
        fa = data.get("fetched_at")
        metas[field] = fa
        if fa and (out["fetched_at"] is None or fa < out["fetched_at"]):
            out["fetched_at"] = fa  # 더 오래된 쪽 기준
    if (metas.get("announcements") is None) != (metas.get("intros") is None):
        out["integrity_warnings"].append("snapshot_incomplete: 스냅샷 파일 중 하나가 없음")
    if metas.get("announcements") and metas.get("intros") \
            and metas["announcements"] != metas["intros"]:
        out["integrity_warnings"].append(
            "fetched_at_mismatch: 두 스냅샷의 수집 시각 불일치 — 부분 동기화 의심")
    _CACHE = out
    return out
```

② `staleness_warning`을 다음 두 함수로 교체:
```python
def data_warnings(data: dict, today: Optional[date] = None) -> list[str]:
    """신선도·정합성 경고 목록 (빈 리스트면 정상)."""
    warnings = list(data.get("integrity_warnings", []))
    fa = data.get("fetched_at")
    if not fa:
        return ["지원사업 데이터가 없습니다. sync_programs를 먼저 실행하세요."]
    try:
        fetched = datetime.fromisoformat(fa).date()
    except ValueError:
        warnings.append(f"invalid_timestamp: fetched_at 해석 불가 ({fa!r}) — 재동기화 권장")
        return warnings
    days = ((today or date.today()) - fetched).days
    if days < 0:
        warnings.append(f"future_timestamp: fetched_at이 미래 시각 ({fa})")
    elif days >= STALE_DAYS:
        warnings.append(f"지원사업 스냅샷이 {days}일 지났습니다. "
                        f"sync_programs로 갱신을 권장합니다.")
    return warnings


def staleness_warning(data: dict, today: Optional[date] = None) -> Optional[str]:
    ws = data_warnings(data, today)
    return "; ".join(ws) if ws else None
```

(주의: 기존 `test_staleness_boundary_and_older_side`는 두 파일의 fetched_at이 다른
픽스처라 이제 fetched_at_mismatch 경고도 함께 붙는다 — 그 테스트는 `"7일" in w`
부분일치 단언이므로 그대로 통과한다. 깨지면 구현을 의심하라.)

③ `server.py` — import에 `import json` 추가, `register_tools` 안 `sync_programs` 아래에:
```python
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
```

④ `SERVER_INSTRUCTIONS`의 도구 선택 목록에 한 줄 추가 (sync_programs 안내 줄 다음):
```
- 데이터 상태·신선도·동기화 이력 확인 → data_status
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q` → 103 passed

- [ ] **Step 5: Commit**

```bash
git add programs.py server.py tests/test_programs.py tests/test_server.py
git commit -m "feat: 신선도·정합성 경고 확장 + data_status 도구 (도구 10개)"
```

---

### Task 7: 실데이터 재동기화 + README·CI + 최종 검증

**Files:**
- Modify: `data/programs/*.json` (재동기화 — URL 정규화 반영), `README.md`
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: 방어 로직 하에서 실 재동기화**

```bash
DATA_GO_KR_KEY=<키> python program_sync.py sync
```
Expected: `status: ok` + before/after 출력 (공고 310→비슷한 수준, 소개 511→비슷). 급감으로 중단되면 원인을 조사해 보고 — **방어 기준을 완화해 통과시키지 말 것**.
검증: `python -X utf8 -c "import json; d=json.load(open('data/programs/intros.json',encoding='utf-8')); print('스킴없음:', sum(1 for i in d['items'] if i['url'] and not i['url'].startswith('http')))"` → `스킴없음: 0`

```bash
git add data/programs
git commit -m "data: 지원사업 재동기화 — URL 정규화 반영"
```

- [ ] **Step 2: CI 워크플로 생성** — `.github/workflows/test.yml`:

```yaml
name: test
on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest tests/ -v
        env:
          PYTHONUTF8: "1"
```

```bash
git add .github/workflows/test.yml
git commit -m "ci: pytest 워크플로 (Windows/Linux, 한글 경로 대응 PYTHONUTF8)"
```

- [ ] **Step 3: README 갱신**

- **fuzzy 예시 수정** (기술 메모): `"감면"↔"경감" 류` → `"세액감면 요건"을 "세액감면요건"으로 붙여 써도 잡는 부분 매칭 류` (bi-gram으로 실제 가능한 예시)
- 도구 표: 제목 "도구 9개" → "도구 10개", 지원사업 표 아래 `data_status` 행 추가 (`(없음)` / 법령·지원사업 데이터 건수·수집 시각·신선도·경고)
- `verify_citation` 반환 설명에 `ambiguous_source` 추가
- 현행성 유지 섹션에 **동기화 안전 정책** 문단: 0건·급감(기존 대비 70% 초과 감소)·스키마 이상 응답은 기존 스냅샷을 보존하고 중단, 임시 파일 → 재파싱 검증 → 원자 교체, 결과에 before/after 건수
- 도구 입력 제한 명시: 범례 줄에 "(`limit`은 1~50)" 추가
- 로드맵 재편: v1.2 **안정화 패치(현재)** → v1.3 창업 특화 3도구 → v1.4 GitHub Actions 주간 동기화 → v2.0 원격 배포
- CI 배지 추가 (선택): `![test](https://github.com/Choihello/startup-law-mcp/actions/workflows/test.yml/badge.svg)`

```bash
git add README.md
git commit -m "docs: README — 도구 10개·동기화 안전 정책·fuzzy 예시 교정·로드맵 재편"
```

- [ ] **Step 4: 최종 검증**

```bash
python -m pytest tests/ -q          # 전부 통과 (103개)
git grep -c "<DATA_GO_KR_KEY 앞 8자>" $(git rev-parse HEAD) ; git grep -c "<LAW_OC 값>" $(git rev-parse HEAD)
```
Expected: 키 검색 두 건 모두 매치 없음(exit 1). CLI 스모크: `python -X utf8 law_search.py verify "중소기업창업 지원법 제2조에 따라"` 가 ok를 반환하는지 확인해 리포트에 수록.
