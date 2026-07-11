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
    assert "d_day" not in rows[0]  # closed 공고에는 d_day 미포함


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


def test_search_nfc_normalization(monkeypatch):
    # NFD로 분해된 한글 데이터도 NFC 질의로 검색돼야 한다
    import unicodedata

    nfd_name = unicodedata.normalize("NFD", "예비창업패키지")
    monkeypatch.setattr(programs, "_CACHE", {
        "announcements": [{"id": "9", "kind": "공고", "name": nfd_name,
                           "category": "", "summary": "", "target": "", "target_age": "",
                           "years": "", "region": "", "org": "",
                           "apply_start": "2026-07-01", "apply_end": "2026-08-30",
                           "contact": "", "url": ""}],
        "intros": [],
        "fetched_at": "2026-07-10T00:00:00+00:00",
    })
    rows = programs.search_programs("예비창업패키지", today=T)["results"]
    assert len(rows) == 1


def test_staleness_boundary_and_older_side(monkeypatch, tmp_path):
    # 두 스냅샷 중 더 오래된 쪽 기준으로, 정확히 7일 경과(경계)에서 경고
    import json as _json

    d = tmp_path / "programs"
    d.mkdir()
    (d / "announcements.json").write_text(_json.dumps(
        {"fetched_at": "2026-07-04T00:00:00+00:00", "count": 0, "items": []}),
        encoding="utf-8")
    (d / "intros.json").write_text(_json.dumps(
        {"fetched_at": "2026-07-09T00:00:00+00:00", "count": 0, "items": []}),
        encoding="utf-8")
    monkeypatch.setattr(programs, "PROGRAMS_DIR", d)
    monkeypatch.setattr(programs, "_CACHE", None)
    data = programs.load_programs()
    assert data["fetched_at"] == "2026-07-04T00:00:00+00:00"
    w = programs.staleness_warning(data, T)
    assert w is not None and "7일" in w
