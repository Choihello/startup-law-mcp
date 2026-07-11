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
