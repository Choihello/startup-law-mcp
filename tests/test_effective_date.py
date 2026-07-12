from datetime import date

import law_search as ls

T_BEFORE = date(2025, 12, 1)   # 시행일(2026-01-01) 전
T_AFTER = date(2026, 7, 12)


def test_law_level_in_force(index):
    r = ls.check_effective_date("테스트창업법", today=T_AFTER)
    assert r["law"]["status"] == "in_force"
    assert r["law"]["effective_date"] == "2026-01-01"
    assert "시행한다" in (r["latest_supplementary"]["effective_clause"] or "")


def test_law_level_upcoming_d_day(index):
    r = ls.check_effective_date("테스트창업법", today=T_BEFORE)
    assert r["law"]["status"] == "upcoming"
    assert r["law"]["d_day"] == 31


def test_article_level_with_transitional(index):
    r = ls.check_effective_date("테스트창업법", article="제2조", today=T_AFTER)
    assert r["article"]["status"] == "in_force"
    assert r["article"]["source_of_date"] == "law"  # 조문 <시행> 없음 → 법령 시행일 사용
    joined = " ".join(t["snippet"] for t in r["transitional_provisions"])
    assert "창업한 기업" in joined  # 부칙 경과조치 발췌
    # 부칙 자체 헤더(제2조(경과조치))는 오탐 제외 — 본문 언급 1건만
    assert len(r["transitional_provisions"]) == 1


def test_article_effective_date_priority(monkeypatch):
    arts = [ls.Article(law_type="법률", source="갱신법", revision="시행 2026.01.01",
                       file="f", chapter="", article="제9조", article_no=9, article_sub=0,
                       article_title="특례", body="본문", effective_date="2026.12.01")]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.check_effective_date("갱신법", article="제9조", today=date(2026, 7, 12))
    assert r["article"]["status"] == "upcoming"
    assert r["article"]["source_of_date"] == "article"  # 조문 시행일이 법령 시행일에 우선


def test_effective_date_errors(index):
    assert "error" in ls.check_effective_date("없는법")
    assert "error" in ls.check_effective_date("테스트창업법", article="제99조")
