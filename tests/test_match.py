"""match_programs 자격 스크리닝 테스트.

실데이터 형식 근거 (2026-07-14 공고 289건 전수, 스펙 참조):
- target_age: "만 20세 미만,만 20세 이상 ~ 만 39세 이하,만 40세 이상"의 콤마 결합
- years: "예비창업자,1년미만,...,10년미만"의 콤마 결합
- region: 시·도 단위 ("전국"/"경기"/"서울"/...)
"""
from datetime import date

import programs

T = date(2026, 7, 11)

FULL_AGE = "만 20세 미만,만 20세 이상 ~ 만 39세 이하,만 40세 이상"


# ---- _parse_age_band ----

def test_parse_age_band():
    assert programs._parse_age_band("만 20세 미만") == (0, 19)
    assert programs._parse_age_band("만 20세 이상 ~ 만 39세 이하") == (20, 39)
    assert programs._parse_age_band("만 40세 이상") == (40, 200)
    assert programs._parse_age_band("만 39세 이하") == (0, 39)  # 일반형(구 픽스처)
    assert programs._parse_age_band("청년이면 됨") is None  # 해석 불가


# ---- _check_age ----

def test_check_age_band_boundaries():
    band = "만 20세 이상 ~ 만 39세 이하"
    assert programs._check_age(20, band)["verdict"] == "match"
    assert programs._check_age(39, band)["verdict"] == "match"
    assert programs._check_age(19, band)["verdict"] == "mismatch"
    assert programs._check_age(40, band)["verdict"] == "mismatch"


def test_check_age_full_coverage_matches_any():
    r = programs._check_age(70, FULL_AGE)
    assert r["verdict"] == "match"
    assert r["evidence"] == FULL_AGE  # 근거는 필드 원문


def test_check_age_unknown_is_honest():
    assert programs._check_age(30, "")["verdict"] == "unknown"
    assert programs._check_age(30, "청년 우대")["verdict"] == "unknown"
    # 일부 토큰만 해석 불가 + 해석된 밴드 불일치 → 탈락 단정 금지
    assert programs._check_age(50, "만 39세 이하,특이토큰")["verdict"] == "unknown"


# ---- _check_years / _check_pre_startup ----

def test_check_years_cap():
    caps = "예비창업자,1년미만,2년미만,3년미만,5년미만,7년미만"
    assert programs._check_years(5, caps)["verdict"] == "match"   # 5 < 7
    assert programs._check_years(6.5, caps)["verdict"] == "match"
    assert programs._check_years(7, caps)["verdict"] == "mismatch"  # 7 < 7 거짓
    assert programs._check_years(0, "예비창업자")["verdict"] == "mismatch"  # 예비 전용
    assert programs._check_years(3, "")["verdict"] == "unknown"
    assert programs._check_years(3, "별도규정")["verdict"] == "unknown"


def test_check_years_legacy_inae_format():
    # 구 픽스처 형식 "N년 이내"도 수용 (이내 = 이하)
    assert programs._check_years(3, "3년 이내")["verdict"] == "match"
    assert programs._check_years(4, "3년 이내")["verdict"] == "mismatch"


def test_check_pre_startup():
    assert programs._check_pre_startup("예비창업자,1년미만")["verdict"] == "match"
    assert programs._check_pre_startup("예비")["verdict"] == "match"  # 구 형식
    assert programs._check_pre_startup("1년미만,3년미만")["verdict"] == "mismatch"
    assert programs._check_pre_startup("")["verdict"] == "unknown"


def test_check_founded_unknown_on_unparseable():
    assert programs._check_founded("별도규정")["verdict"] == "unknown"
    assert programs._check_founded("예비창업자,별도규정")["verdict"] == "unknown"
    assert programs._check_founded("예비창업자,3년미만")["verdict"] == "match"


# ---- _check_region ----

def test_check_region():
    assert programs._check_region("대구", "전국")["verdict"] == "match"
    assert programs._check_region("대구", "대구")["verdict"] == "match"
    assert programs._check_region("대구광역시", "대구")["verdict"] == "match"  # 양방향 부분일치
    assert programs._check_region("대구", "경기")["verdict"] == "mismatch"
    assert programs._check_region("대구", "")["verdict"] == "unknown"
    assert programs._check_region("충청남도", "충남")["verdict"] == "match"
    assert programs._check_region("전라북도", "전북")["verdict"] == "match"
    assert programs._check_region("경기도", "경기")["verdict"] == "match"
    assert programs._check_region("충청남도", "충북")["verdict"] == "mismatch"


# ---- _needs_review ----

def test_needs_review_extracts_special_conditions():
    text = "공고일 기준 여성 예비창업자로서 대구광역시에 본사 소재 예정인 자"
    snippets = programs._needs_review(text)
    assert any("여성" in s for s in snippets)
    assert any("소재" in s for s in snippets)
    assert programs._needs_review("예비창업자") == []
    assert programs._needs_review("") == []


# ---- match_programs 본체 ----

def _cache(monkeypatch, items):
    monkeypatch.setattr(programs, "_CACHE", {
        "announcements": items, "intros": [],
        "fetched_at": "2026-07-10T00:00:00+00:00", "integrity_warnings": []})


def _ann(i, **kw):
    base = {"id": str(i), "kind": "공고", "name": f"공고{i}", "category": "",
            "summary": "", "target": "", "target_age": FULL_AGE,
            "years": "예비창업자,1년미만,2년미만,3년미만,5년미만,7년미만",
            "region": "전국", "apply_start": "2026-07-01",
            "apply_end": "2026-08-30", "org": "", "contact": "",
            "url": f"https://www.k-startup.go.kr/{i}"}
    base.update(kw)
    return base


def test_match_excludes_mismatch_and_counts(monkeypatch):
    _cache(monkeypatch, [
        _ann(1, target_age="만 20세 이상 ~ 만 39세 이하"),
        _ann(2, target_age="만 40세 이상"),
    ])
    r = programs.match_programs(age=45, today=T)
    assert [row["name"] for row in r["results"]] == ["공고2"]
    assert r["excluded"] == 1
    assert r["results"][0]["checks"]["age"]["verdict"] == "match"
    assert r["results"][0]["checks"]["age"]["evidence"] == "만 40세 이상"


def test_match_unknown_included_with_label(monkeypatch):
    _cache(monkeypatch, [_ann(1, target_age="청년 우대")])
    r = programs.match_programs(age=30, today=T)
    assert r["results"][0]["checks"]["age"]["verdict"] == "unknown"
    assert r["excluded"] == 0


def test_match_pre_startup_and_years(monkeypatch):
    _cache(monkeypatch, [
        _ann(1, years="예비창업자"),
        _ann(2, years="1년미만,2년미만,3년미만"),
    ])
    pre = programs.match_programs(pre_startup=True, today=T)
    assert [row["name"] for row in pre["results"]] == ["공고1"]
    running = programs.match_programs(years=2, today=T)
    assert [row["name"] for row in running["results"]] == ["공고2"]


def test_match_region_and_multi_condition(monkeypatch):
    _cache(monkeypatch, [
        _ann(1, region="대구"),
        _ann(2, region="경기"),
        _ann(3, region="전국", target_age="만 20세 이상 ~ 만 39세 이하"),
    ])
    r = programs.match_programs(age=45, region="대구", today=T)
    # 공고2: 지역 탈락 / 공고3: 나이 탈락 / 공고1: 둘 다 통과(전연령+대구)
    assert [row["name"] for row in r["results"]] == ["공고1"]
    assert r["excluded"] == 2
    assert set(r["results"][0]["checks"]) == {"age", "region"}


def test_match_only_open_announcements(monkeypatch):
    _cache(monkeypatch, [
        _ann(1, apply_end="2026-07-01"),              # closed → 제외 (excluded 미집계)
        _ann(2, apply_start="2026-08-01", apply_end="2026-08-20"),  # upcoming → 포함
    ])
    r = programs.match_programs(age=30, today=T)
    assert [row["name"] for row in r["results"]] == ["공고2"]
    assert r["results"][0]["status"] == "upcoming"
    assert r["excluded"] == 0


def test_match_sorted_by_deadline_and_limit(monkeypatch):
    _cache(monkeypatch, [
        _ann(1, apply_end="2026-08-30"),
        _ann(2, apply_end="2026-07-20"),
        _ann(3, apply_end="2026-08-01"),
    ])
    r = programs.match_programs(age=30, today=T)
    assert [row["apply_end"] for row in r["results"]] == \
        ["2026-07-20", "2026-08-01", "2026-08-30"]
    assert len(programs.match_programs(age=30, limit=1, today=T)["results"]) == 1
    assert programs.match_programs(age=30, limit=-5, today=T)["results"]  # clamp → 1


def test_match_keyword_labels_not_filters(monkeypatch):
    _cache(monkeypatch, [
        _ann(1, summary="바이오 헬스케어 스타트업 지원"),
        _ann(2, summary="일반 사업화 지원"),
    ])
    r = programs.match_programs(age=30, keyword="바이오", today=T)
    assert len(r["results"]) == 2  # keyword는 탈락 사유 아님
    hits = {row["name"]: row["keyword_hit"] for row in r["results"]}
    assert hits == {"공고1": True, "공고2": False}


def test_match_needs_review_surfaces(monkeypatch):
    _cache(monkeypatch, [_ann(1, target="여성 예비창업자 대상")])
    r = programs.match_programs(age=30, today=T)
    assert any("여성" in s for s in r["results"][0]["needs_review"])


def test_match_warning_propagates(monkeypatch):
    _cache(monkeypatch, [_ann(1)])
    monkeypatch.setitem(programs._CACHE, "fetched_at", "2026-07-01T00:00:00+00:00")
    assert "10일" in programs.match_programs(age=30, today=T)["warning"]


def test_match_pre_startup_false_excludes_pre_only(monkeypatch):
    _cache(monkeypatch, [
        _ann(1, years="예비창업자"),
        _ann(2, years="예비창업자,1년미만,2년미만"),
    ])
    r = programs.match_programs(pre_startup=False, today=T)
    assert [row["name"] for row in r["results"]] == ["공고2"]
    assert r["excluded"] == 1


def test_match_pre_startup_false_with_years_no_duplicate_check(monkeypatch):
    _cache(monkeypatch, [_ann(1, years="예비창업자,3년미만")])
    r = programs.match_programs(pre_startup=False, years=2, today=T)
    assert set(r["results"][0]["checks"]) == {"years"}


# ---- 공유 픽스처(실데이터 형식) 통합 ----

def test_match_with_shared_fixture(programs_index):
    # T 기준 공고1(예비·전연령·전국)은 closing_soon, 공고4는 closed
    r = programs.match_programs(pre_startup=True, region="대구", today=T)
    names = [row["name"] for row in r["results"]]
    assert names == ["2026년 예비창업패키지 예비창업자 모집 공고"]
    assert r["results"][0]["status"] == "closing_soon"
    assert r["excluded"] == 2  # 공고2·3 — 예비창업자 토큰 없음


# ---- 실데이터 스모크 (공고 전수 파싱율 — 스냅샷은 커밋되어 CI에서도 실행; 부재 시에만 skip) ----
import json as _json
from pathlib import Path

import pytest

_REAL = Path(programs.__file__).parent / "data" / "programs" / "announcements.json"


@pytest.mark.skipif(not _REAL.exists(), reason="실데이터 스냅샷 없음")
def test_real_snapshot_band_parse_rate():
    items = _json.loads(_REAL.read_text(encoding="utf-8"))["items"]
    assert items
    age_unknown = sum(1 for it in items
                      if programs._check_age(30, it.get("target_age"))["verdict"]
                      == "unknown")
    years_unknown = sum(1 for it in items
                        if programs._check_years(3, it.get("years"))["verdict"]
                        == "unknown")
    # 구조화 필드 파싱 실패율 5% 미만 — 초과하면 K-Startup 형식 변화 신호
    assert age_unknown / len(items) < 0.05, f"age unknown {age_unknown}/{len(items)}"
    assert years_unknown / len(items) < 0.05, f"years unknown {years_unknown}/{len(items)}"
