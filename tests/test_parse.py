import json
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
