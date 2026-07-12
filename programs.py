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
