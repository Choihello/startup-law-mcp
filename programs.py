"""지원사업(K-Startup 공고·사업소개) 조회 모듈.

data/programs/*.json 스냅샷을 로드해 상태 계산·검색·조회를 제공한다.
토크나이저·스니펫·NFC는 law_search를 재사용한다. IDF는 미적용 —
공고 코퍼스는 수백 건 규모라 TF + 사업명 가중으로 충분.
"""
from __future__ import annotations

import json
import re
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


def data_warnings(data: dict, today: Optional[date] = None) -> list[str]:
    """신선도·정합성 경고 목록 (빈 리스트면 정상)."""
    warnings = list(data.get("integrity_warnings", []))
    fa = data.get("fetched_at")
    if not fa:
        warnings.append("지원사업 데이터가 없습니다. sync_programs를 먼저 실행하세요.")
        return warnings
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


_SEARCH_FIELDS = ("name", "category", "summary", "target", "region", "org")


def _searchable_text(item: dict) -> str:
    return ls._nfc(" ".join(str(item.get(k, "")) for k in _SEARCH_FIELDS))


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
    limit = max(1, min(limit, 50))
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
                if tok in ls._nfc(str(it.get("name", ""))):
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
    limit = max(1, min(limit, 50))
    data = load_programs()
    rows = []
    for it in data["announcements"]:
        st = program_status(it, today)
        if st not in ("open", "closing_soon", "upcoming"):
            continue
        rows.append(_result_row(it, st, today))
    rows.sort(key=lambda r: r.get("apply_end") or "9999-12-31")
    return {"results": rows[:limit], "warning": staleness_warning(data, today)}


# ---- match_programs: 프로필 기반 자격 스크리닝 ----
# 판정 신호는 K-Startup 구조화 필드(target_age/years/region) — 2026-07-14 전수
# 확인 기준 결측 0·자유텍스트와 충돌 0 (스펙 참조). 자유텍스트(target)는 판정에
# 쓰지 않고 특수조건 감지(needs_review)에만 사용.

_AGE_PART = re.compile(r"만\s*(\d+)세\s*(미만|이하|이상)")
_YEARS_CAP = re.compile(r"(\d+)\s*년\s*(미만|이내|이하)")
_UNKNOWN_EVIDENCE = "원문 확인 필요"

_REVIEW_TERMS = ("여성", "대학생", "대학(원)생", "대학원생", "재직자", "소상공인",
                 "재도전", "폐업", "재창업", "컨소시엄", "소재", "이전", "미가맹",
                 "장애인", "외국인")


def _parse_age_band(token: str) -> Optional[tuple[int, int]]:
    """나이 밴드 토큰 → (lo, hi) 폐구간. '만 N세' 표현이 없으면 None."""
    lo, hi, found = 0, 200, False
    for m in _AGE_PART.finditer(token):
        n, kind = int(m.group(1)), m.group(2)
        found = True
        if kind == "미만":
            hi = min(hi, n - 1)
        elif kind == "이하":
            hi = min(hi, n)
        else:
            lo = max(lo, n)
    return (lo, hi) if found else None


def _split_tokens(raw) -> tuple[str, list[str]]:
    text = ls._nfc(str(raw or "")).strip()
    return text, [t.strip() for t in text.split(",") if t.strip()]


def _check_age(age: int, target_age) -> dict:
    raw, tokens = _split_tokens(target_age)
    if not tokens:
        return {"verdict": "unknown", "evidence": _UNKNOWN_EVIDENCE}
    bands = [_parse_age_band(t) for t in tokens]
    known = [b for b in bands if b is not None]
    if not known:
        return {"verdict": "unknown", "evidence": raw}
    if any(lo <= age <= hi for lo, hi in known):
        return {"verdict": "match", "evidence": raw}
    if len(known) < len(bands):  # 해석 못한 토큰이 남음 — 탈락 단정 금지
        return {"verdict": "unknown", "evidence": raw}
    return {"verdict": "mismatch", "evidence": raw}


def _check_pre_startup(tokens_raw) -> dict:
    raw, tokens = _split_tokens(tokens_raw)
    if not tokens:
        return {"verdict": "unknown", "evidence": _UNKNOWN_EVIDENCE}
    if any(t.startswith("예비") for t in tokens):
        return {"verdict": "match", "evidence": raw}
    return {"verdict": "mismatch", "evidence": raw}


def _check_founded(tokens_raw) -> dict:
    """pre_startup=False(기창업, 업력 미상) — 예비창업자 전용 공고만 걸러낸다."""
    raw, tokens = _split_tokens(tokens_raw)
    if not tokens:
        return {"verdict": "unknown", "evidence": _UNKNOWN_EVIDENCE}
    if all(t.startswith("예비") for t in tokens):
        return {"verdict": "mismatch", "evidence": raw}
    if any(_YEARS_CAP.search(t) for t in tokens if not t.startswith("예비")):
        return {"verdict": "match", "evidence": raw}
    return {"verdict": "unknown", "evidence": raw}


def _check_years(years: float, tokens_raw) -> dict:
    raw, tokens = _split_tokens(tokens_raw)
    if not tokens:
        return {"verdict": "unknown", "evidence": _UNKNOWN_EVIDENCE}
    caps, unparsed = [], False
    for t in tokens:
        if t.startswith("예비"):
            continue
        m = _YEARS_CAP.search(t)
        if m:
            caps.append((int(m.group(1)), m.group(2)))
        else:
            unparsed = True
    if caps:
        if any(years < n if kind == "미만" else years <= n for n, kind in caps):
            return {"verdict": "match", "evidence": raw}
        if unparsed:
            return {"verdict": "unknown", "evidence": raw}
        return {"verdict": "mismatch", "evidence": raw}
    if unparsed:
        return {"verdict": "unknown", "evidence": raw}
    return {"verdict": "mismatch", "evidence": raw}  # 예비창업자 전용 공고


_REGION_ALIASES = {
    "충청남도": "충남", "충청북도": "충북", "경상남도": "경남", "경상북도": "경북",
    "전라남도": "전남", "전라북도": "전북", "전북특별자치도": "전북",
    "강원도": "강원", "강원특별자치도": "강원", "경기도": "경기",
    "제주도": "제주", "제주특별자치도": "제주", "세종특별자치시": "세종",
}


def _norm_region(s: str) -> str:
    s = ls._nfc(str(s)).strip()
    return _REGION_ALIASES.get(s, s)


def _check_region(region: str, item_region) -> dict:
    raw = ls._nfc(str(item_region or "")).strip()
    if not raw:
        return {"verdict": "unknown", "evidence": _UNKNOWN_EVIDENCE}
    if raw == "전국":
        return {"verdict": "match", "evidence": "전국"}
    raw_n = _norm_region(item_region)
    q = _norm_region(region)
    if q and (q in raw_n or raw_n in q):
        return {"verdict": "match", "evidence": raw}
    return {"verdict": "mismatch", "evidence": raw}


def _needs_review(target_text) -> list[str]:
    """지원대상 자유텍스트에서 구조화 필드로 판정 불가한 특수조건을 발췌."""
    text = ls._nfc(str(target_text or ""))
    out: list[str] = []
    for term in _REVIEW_TERMS:
        pos = text.find(term)
        if pos < 0:
            continue
        snip = ls.make_snippet(text, pos)
        if snip and snip not in out:
            out.append(snip)
    return out


def match_programs(age: Optional[int] = None, region: Optional[str] = None,
                   pre_startup: Optional[bool] = None, years: Optional[float] = None,
                   keyword: Optional[str] = None, limit: int = 20,
                   today: Optional[date] = None) -> dict:
    """프로필 기반 자격 스크리닝 — 탈락 사유 확인된 공고만 제외, 마감순.

    스크리닝이지 판정이 아니다: 제공된 프로필 인자만 검사하고, 해석 불가
    조건은 unknown으로 남긴다. keyword는 탈락 사유가 아니라 라벨.
    """
    today = today or date.today()
    limit = max(1, min(limit, 50))
    data = load_programs()
    kw_tokens = ls.tokenize(keyword) if keyword else []
    results: list[dict] = []
    excluded = 0
    for it in data["announcements"]:
        st = program_status(it, today)
        if st not in ("open", "closing_soon", "upcoming"):
            continue
        checks: dict[str, dict] = {}
        if age is not None:
            checks["age"] = _check_age(age, it.get("target_age"))
        if pre_startup is not None:
            if pre_startup:
                checks["pre_startup"] = _check_pre_startup(it.get("years"))
            elif years is None:
                checks["pre_startup"] = _check_founded(it.get("years"))
        if years is not None:
            checks["years"] = _check_years(years, it.get("years"))
        if region is not None:
            checks["region"] = _check_region(region, it.get("region"))
        if any(c["verdict"] == "mismatch" for c in checks.values()):
            excluded += 1
            continue
        row = _result_row(it, st, today)
        row["checks"] = checks
        review = _needs_review(it.get("target"))
        if review:
            row["needs_review"] = review
        if kw_tokens:
            text = _searchable_text(it)
            row["keyword_hit"] = any(t in text for t in kw_tokens)
        results.append(row)
    results.sort(key=lambda r: r.get("apply_end") or "9999-12-31")
    return {"results": results[:limit], "excluded": excluded,
            "warning": staleness_warning(data, today)}
