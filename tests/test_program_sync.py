import json

import pytest

import program_sync


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(program_sync, "PROGRAMS_DIR", tmp_path / "programs")
    pages = {
        ("announcement", 1): {"totalCount": 400, "data": [
            {"pbanc_sn": "1", "biz_pbanc_nm": "A공고", "rcrt_prgs_yn": "Y",
             "pbanc_rcpt_end_dt": "20260801"},
            {"pbanc_sn": "2", "biz_pbanc_nm": "B공고", "rcrt_prgs_yn": "N",
             "pbanc_rcpt_end_dt": "20990101"},  # 플래그 N이지만 마감 미래 → 보존
        ]},
        ("announcement", 2): {"totalCount": 400, "data": [
            {"pbanc_sn": "3", "biz_pbanc_nm": "C공고", "rcrt_prgs_yn": "N",
             "pbanc_rcpt_end_dt": "20200101"},
        ]},
        ("announcement", 3): {"totalCount": 400, "data": [
            {"pbanc_sn": "4", "biz_pbanc_nm": "D공고", "rcrt_prgs_yn": "N",
             "pbanc_rcpt_end_dt": "20200102"},
        ]},
        ("announcement", 4): {"totalCount": 400, "data": [
            {"pbanc_sn": "5", "biz_pbanc_nm": "E공고", "rcrt_prgs_yn": "Y",
             "pbanc_rcpt_end_dt": "20990201"},  # 조기중단으로 도달하지 않아야 함
        ]},
        ("intro", 1): {"totalCount": 1, "data": [{"supt_biz_titl_nm": "예비창업패키지"}]},
    }

    def fake_page(key, target, page=1, per_page=100):
        return pages.get((target, page), {"totalCount": 0, "data": []})

    monkeypatch.setattr(program_sync, "fetch_page", fake_page)
    return tmp_path


def test_fetch_all_paginates(env):
    # 원시 전량 수집 — 빈 페이지에서 중단 (필터 없음)
    items = program_sync.fetch_all("k", "announcement")
    assert len(items) == 5


def test_fetch_current_filters_and_early_stops(env):
    items = program_sync.fetch_current_announcements("k")
    ids = [it["pbanc_sn"] for it in items]
    # Y 1건 + 마감 미래 N 1건 보존, 0건 페이지(2·3p) 2연속에서 중단 → 4p 미도달
    assert ids == ["1", "2"]


def test_sync_writes_snapshots(env):
    result = program_sync.sync("k")
    assert result["announcements"] == 2
    assert result["intros"] == 1
    ann = json.loads((env / "programs" / "announcements.json").read_text(encoding="utf-8"))
    assert ann["count"] == 2
    assert ann["fetched_at"]
    assert ann["items"][0]["kind"] == "공고"
    intro = json.loads((env / "programs" / "intros.json").read_text(encoding="utf-8"))
    assert intro["items"][0]["kind"] == "사업소개"
    assert intro["items"][0]["name"] == "예비창업패키지"


def test_sync_preserves_snapshot_on_failure(env, monkeypatch):
    program_sync.sync("k")  # 정상 스냅샷 생성
    before = (env / "programs" / "announcements.json").read_text(encoding="utf-8")

    def boom(key, target, page=1, per_page=100):
        raise RuntimeError("api down")

    monkeypatch.setattr(program_sync, "fetch_page", boom)
    with pytest.raises(RuntimeError):
        program_sync.sync("k")
    # 실패한 동기화가 기존 스냅샷을 건드리지 않아야 함 (원자성)
    assert (env / "programs" / "announcements.json").read_text(encoding="utf-8") == before
