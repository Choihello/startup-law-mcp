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


# ---- _check_region ----

def test_check_region():
    assert programs._check_region("대구", "전국")["verdict"] == "match"
    assert programs._check_region("대구", "대구")["verdict"] == "match"
    assert programs._check_region("대구광역시", "대구")["verdict"] == "match"  # 양방향 부분일치
    assert programs._check_region("대구", "경기")["verdict"] == "mismatch"
    assert programs._check_region("대구", "")["verdict"] == "unknown"


# ---- _needs_review ----

def test_needs_review_extracts_special_conditions():
    text = "공고일 기준 여성 예비창업자로서 대구광역시에 본사 소재 예정인 자"
    snippets = programs._needs_review(text)
    assert any("여성" in s for s in snippets)
    assert any("소재" in s for s in snippets)
    assert programs._needs_review("예비창업자") == []
    assert programs._needs_review("") == []
