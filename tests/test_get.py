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
