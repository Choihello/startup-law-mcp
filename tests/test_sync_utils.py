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
