import law_search as ls


def test_delegation_law_to_decree(index):
    r = ls.delegation_map("테스트창업법")
    assert r["role"] == "법률"
    assert r["subordinates"] == ["테스트창업법 시행령"]
    entries = {e["article"]: e for e in r["delegating_articles"]}
    assert "제2조" in entries  # "대통령령으로 정한다" 위임 문구 보유
    e = entries["제2조"]
    assert any("대통령령으로 정한" in p for p in e["phrases"])
    cites = [d["citation"] for d in e["delegated_to"]]
    assert "테스트창업법 시행령 제4조" in cites  # '법 제2조' 축약 역매칭


def test_delegation_abbrev_boundary(index):
    # 시행령 제3조는 '테스트창업법 제2조'(전체 이름) 참조 — 축약 매칭에 잡히면 안 됨
    r = ls.delegation_map("테스트창업법", article="제2조")
    e = r["delegating_articles"][0]
    cites = [d["citation"] for d in e["delegated_to"]]
    assert "테스트창업법 시행령 제3조" not in cites


def test_delegation_reverse_direction(index):
    r = ls.delegation_map("테스트창업법 시행령")
    assert r["role"] == "시행령"
    assert r["parent"] == "테스트창업법"
    linked = {a["article"]: a for a in r["articles_with_links"]}
    assert "제4조" in linked
    up = linked["제4조"]["upward"][0]
    assert up["citation"] == "테스트창업법 제2조"
    assert up["found"] is True


def test_delegation_sync_check(monkeypatch):
    arts = [
        ls.Article(law_type="법률", source="갱신법", revision="시행 2026.06.01", file="f",
                   chapter="", article="제1조", article_no=1, article_sub=0,
                   article_title="목적", body="세부 사항은 대통령령으로 정한다."),
        ls.Article(law_type="대통령령", source="갱신법 시행령", revision="시행 2025.01.01",
                   file="f", chapter="", article="제1조", article_no=1, article_sub=0,
                   article_title="목적", body="법 제1조에 따른다."),
    ]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.delegation_map("갱신법")
    assert r["sync_check"]["status"] == "review_needed"


def test_delegation_unknown_source(index):
    assert "error" in ls.delegation_map("없는법")
