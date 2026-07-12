import law_search as ls


def test_verify_ok(index):
    r = ls.verify_citation("테스트창업법 제2조에 따라 창업기업을 정의한다.")
    assert len(r) == 1
    assert r[0]["status"] == "ok"
    assert r[0]["citation"] == "테스트창업법 제2조"


def test_verify_ok_with_matching_title(index):
    r = ls.verify_citation("테스트창업법 제2조(정의)에 따르면")
    assert r[0]["status"] == "ok"
    assert r[0]["title_verified"] is True


def test_verify_content_mismatch(index):
    # 존재하는 조문번호 + 엉뚱한 제목 = 내용 환각
    r = ls.verify_citation("테스트창업법 제2조(창업지원센터 설치)에 따라")
    assert r[0]["status"] == "content_mismatch"
    assert r[0]["actual_title"] == "정의"


def test_verify_not_found(index):
    r = ls.verify_citation("테스트창업법 제99조에 따라")
    assert r[0]["status"] == "not_found"
    assert "제99조" in r[0]["citation"]
    assert "실재" in r[0]["message"]


def test_verify_unknown_source(index):
    r = ls.verify_citation("무명가상법 제1조에 따라")
    assert r[0]["status"] == "unknown_source"


def test_verify_definition_paren_not_title(index):
    # "(이하 ...)"는 제목이 아니라 부연 — 제목검증 제외, ok
    r = ls.verify_citation('테스트창업법 제2조(이하 "창업조항")에 따라')
    assert r[0]["status"] == "ok"
    assert r[0]["title_verified"] is False


def test_verify_multiple_citations(index):
    text = "테스트창업법 제1조와 테스트창업법 제99조를 근거로 한다."
    r = ls.verify_citation(text)
    statuses = [x["status"] for x in r]
    assert statuses == ["ok", "not_found"]


def test_verify_curly_quote_paren_not_title(index):
    # 곡선따옴표 부연 괄호도 제목이 아님 — 제목검증 제외
    r = ls.verify_citation("테스트창업법 제2조(" + chr(0x201C) + "창업조항" + chr(0x201D) + ")에 따라")
    assert r[0]["status"] == "ok"
    assert r[0]["title_verified"] is False


def test_verify_abbreviated_title_ok(index):
    # 인용 제목이 실제 제목("세액감면 요건")의 부분이면 축약 인용으로 허용
    r = ls.verify_citation("테스트창업법 시행령 제3조(세액감면)에 근거하여")
    assert r[0]["status"] == "ok"
    assert r[0]["title_verified"] is True


def test_verify_variant_title_bigram_ok(index):
    # 이표기("세액감면의 요건" vs 실제 "세액감면 요건") — bigram Jaccard >= 0.4 허용
    r = ls.verify_citation("테스트창업법 시행령 제3조(세액감면의 요건)에 따라")
    assert r[0]["status"] == "ok"


def test_verify_modifier_appended_title_is_mismatch(index):
    # 실제 제목("정의")에 수식어를 덧붙인 인용은 축약이 아니라 환각
    r = ls.verify_citation("테스트창업법 제2조(정의 및 적용범위)에 따라")
    assert r[0]["status"] == "content_mismatch"


def test_article_range_exact_source(index):
    # 시행령 조문(제2조·제3조)이 본법 범위에 혼입되면 4개가 된다
    rng = ls._article_range_for("테스트창업법", ls.load_index())
    assert "총 3개" in rng


def test_verify_inferred_source(index):
    r = ls.verify_citation("테스트창업법은 창업 지원의 근간이 되는 법률이다. 한편 여기서 제2조에 따르면")
    assert r[0]["status"] == "ok"
    assert r[0].get("source_inference") == "inferred"


def test_verify_explicit_has_no_inference_flag(index):
    r = ls.verify_citation("테스트창업법 제2조에 따라")
    assert r[0]["status"] == "ok"
    assert "source_inference" not in r[0]


def test_verify_ambiguous_source(index):
    text = "테스트창업법과 그 하위법령인 테스트창업법 시행령을 함께 검토한다. 이때 제2조는"
    r = ls.verify_citation(text)
    assert r[0]["status"] == "ambiguous_source"
    assert "테스트창업법" in r[0]["candidates"]
    assert "테스트창업법 시행령" in r[0]["candidates"]
