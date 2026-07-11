import law_sync


def test_as_list_none():
    assert law_sync._as_list(None) == []


def test_as_list_single_dict():
    assert law_sync._as_list({"a": 1}) == [{"a": 1}]


def test_as_list_passthrough():
    assert law_sync._as_list([1, 2]) == [1, 2]


def test_fmt_date_yyyymmdd():
    assert law_sync._fmt_date("20260101") == "2026.01.01"
    assert law_sync._fmt_date(20241022) == "2024.10.22"


def test_fmt_date_passthrough():
    assert law_sync._fmt_date("2026.01.01") == "2026.01.01"
    assert law_sync._fmt_date(None) == ""


def test_unit_text_flattens_nested_list_mok_content():
    """실 API 응답 회귀 테스트: 세율표처럼 가./나. 아래 1)/2) 소항목이 있으면
    목내용이 문자열이 아니라 [[str, str, ...]] 형태 중첩 list로 온다.
    str()로 감싸면 "['...', '...']" 파이썬 repr이 그대로 본문에 박히던 버그."""
    unit = {
        "조문번호": "6", "조문여부": "조문", "조문제목": "세액감면",
        "조문내용": "제6조(세액감면) 다음 각 호에 따라 감면한다.",
        "항": [{
            "항번호": "①", "항내용": "① 다음 각 호와 같다.",
            "호": [{
                "호번호": "1.", "호내용": "1. 창업중소기업의 경우",
                "목": [{
                    "목번호": "가.",
                    "목내용": [["가. 2025년 이전 창업한 경우",
                               "  1) 청년창업중소기업: 100분의 100"]],
                }],
            }],
        }],
    }
    text = law_sync._unit_text(unit)
    assert "[['" not in text
    assert "가. 2025년 이전 창업한 경우" in text
    assert "1) 청년창업중소기업: 100분의 100" in text
