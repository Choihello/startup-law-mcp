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
