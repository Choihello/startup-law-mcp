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
