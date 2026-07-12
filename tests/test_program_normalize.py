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


def test_normalize_intro_url_gets_scheme():
    recs = [program_sync.normalize_intro(r) for r in _fx()["intro_items"]]
    for r in recs:
        assert r["url"] == "" or r["url"].startswith(("https://", "http://"))
    assert any(r["url"].startswith("https://") for r in recs)  # 실 fixture는 www. 시작
