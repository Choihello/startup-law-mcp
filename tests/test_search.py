import law_search as ls


def test_tokenize_strips_josa_and_stopwords():
    toks = ls.tokenize("창업기업의 세액감면 요건은 무엇")
    assert "창업기업" in toks   # 조사 "의" 제거
    assert "세액감면" in toks
    assert "요건" in toks       # 조사 "은" 제거
    assert "무엇" not in toks   # 불용어 제거


def test_search_finds_relevant_articles(index):
    results = ls.search("세액감면 요건")
    citations = [r["citation"] for r in results]
    assert "테스트창업법 시행령 제3조" in citations
    assert "테스트창업법 제2조" in citations
    assert all(r["score"] > 0 for r in results)


def test_search_source_filter(index):
    results = ls.search("세액감면", source="시행령")
    assert results
    assert all("시행령" in r["source"] for r in results)


def test_search_title_boost(index):
    # 조문제목 매칭("정의")이 본문-only 매칭보다 상위
    results = ls.search("정의")
    assert results[0]["citation"] == "테스트창업법 제2조"


def test_search_fuzzy_bigram(index):
    # 본문 표기는 "세액감면 요건"(공백) — 붙여 쓴 질의는 정확 매칭 실패,
    # fuzzy(음절 bi-gram)로만 잡힌다
    assert ls.search("세액감면요건", fuzzy=False) == []
    assert len(ls.search("세액감면요건", fuzzy=True)) >= 1


def test_source_match_normalization():
    assert ls.source_match("부정경쟁방지법", "부정경쟁방지 및 영업비밀보호에 관한 법률") is False  # 약칭은 v1 미지원 — 정직하게
    assert ls.source_match("부정경쟁방지", "부정경쟁방지 및 영업비밀보호에 관한 법률") is True
    assert ls.source_match("영업비밀 보호", "부정경쟁방지 및 영업비밀보호에 관한 법률") is True
