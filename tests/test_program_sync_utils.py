import pytest

import program_sync


def test_date_norm_compact():
    assert program_sync._date_norm("20260711") == "2026-07-11"


def test_date_norm_variants():
    assert program_sync._date_norm("2026-07-11") == "2026-07-11"
    assert program_sync._date_norm("2026.07.11") == "2026-07-11"


def test_date_norm_invalid():
    assert program_sync._date_norm(None) == ""
    assert program_sync._date_norm("상시") == ""
    assert program_sync._date_norm("") == ""


def test_get_json_surfaces_non_json_error(monkeypatch):
    class FakeResp:
        def read(self):
            return "<OpenAPI_ServiceResponse>SERVICE ERROR</OpenAPI_ServiceResponse>".encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(program_sync.urllib.request, "urlopen",
                        lambda req, timeout=30: FakeResp())
    with pytest.raises(RuntimeError, match="JSON이 아닌 응답"):
        program_sync._get_json("https://example.com/x")


def test_normalize_url_variants():
    f = program_sync._normalize_url
    assert f("www.k-startup.go.kr/a?b=1") == "https://www.k-startup.go.kr/a?b=1"
    assert f("/web/contents/x.do") == "https://www.k-startup.go.kr/web/contents/x.do"
    assert f("https://already.example/x") == "https://already.example/x"
    assert f("http://legacy.example/x") == "http://legacy.example/x"
    assert f("ftp://bad.example/x") == ""
    assert f("javascript:alert(1)") == ""
    assert f(None) == ""
