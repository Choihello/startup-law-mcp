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
