from datetime import date

import programs

T = date(2026, 7, 11)


def test_program_status_boundaries():
    mk = lambda s, e: {"apply_start": s, "apply_end": e}
    assert programs.program_status(mk("2026-07-01", "2026-07-11"), T) == "closing_soon"  # 마감 당일
    assert programs.program_status(mk("2026-07-01", "2026-07-10"), T) == "closed"
    assert programs.program_status(mk("2026-07-01", "2026-07-18"), T) == "closing_soon"  # D-7
    assert programs.program_status(mk("2026-07-01", "2026-07-19"), T) == "open"          # D-8
    assert programs.program_status(mk("2026-07-12", "2026-08-01"), T) == "upcoming"
    assert programs.program_status({}, T) == "unknown"


def test_search_returns_announcement_and_intro(programs_index):
    r = programs.search_programs("예비창업패키지", today=T)
    kinds = {row["kind"] for row in r["results"]}
    assert kinds == {"공고", "사업소개"}
    assert r["warning"] is None  # 스냅샷 1일 경과 — 신선


def test_search_excludes_closed_by_default(programs_index):
    assert programs.search_programs("창업사관학교", today=T)["results"] == []
    rows = programs.search_programs("창업사관학교", include_closed=True, today=T)["results"]
    assert len(rows) == 1
    assert rows[0]["status"] == "closed"


def test_search_status_filter_announcements_only(programs_index):
    rows = programs.search_programs("창업", status="open", today=T)["results"]
    assert rows
    assert all(row["kind"] == "공고" and row["status"] == "open" for row in rows)


def test_list_open_sorted_by_deadline(programs_index):
    rows = programs.list_open_programs(today=T)["results"]
    assert len(rows) == 3  # closed 제외
    ends = [row["apply_end"] for row in rows]
    assert ends == sorted(ends)
    assert all(row["status"] in ("open", "closing_soon", "upcoming") for row in rows)
    assert rows[0]["d_day"] == 4  # 예비창업패키지, 07-15 마감


def test_get_program_detail(programs_index):
    r = programs.get_program("예비창업패키지", today=T)
    assert 1 <= len(r["results"]) <= 5
    first = r["results"][0]
    assert first["kind"] == "공고"
    assert first["status"] == "closing_soon"
    assert first["d_day"] == 4


def test_staleness_warning():
    old = {"fetched_at": "2026-07-01T00:00:00+00:00"}
    w = programs.staleness_warning(old, T)
    assert w is not None and "10일" in w
    assert programs.staleness_warning({"fetched_at": "2026-07-10T00:00:00+00:00"}, T) is None
    assert "없습니다" in programs.staleness_warning({}, T)
