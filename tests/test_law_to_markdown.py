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
