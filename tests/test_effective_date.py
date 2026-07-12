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


def test_transitional_precision(monkeypatch):
    # 후행 경계·타법개정 제외 — '제2조' 조회가 의2/제3호/생략 보일러플레이트에 오염되지 않아야
    suppl_body = (
        "제1조(시행일) 이 법은 2026년 1월 1일부터 시행한다.\n"
        "제2조(경과조치) 제2조의2 및 제2조제3호는 생략한다. 다만 종전의 제2조에 따른 처분은 유효하다.\n"
        "제3조(다른 법률의 개정) 제2조부터 제21조까지 생략")
    arts = [
        ls.Article(law_type="법률", source="정밀법", revision="시행 2026.01.01", file="f",
                   chapter="", article="제2조", article_no=2, article_sub=0,
                   article_title="정의", body="본문"),
        ls.Article(law_type="법률", source="정밀법", revision="시행 2026.01.01", file="f",
                   chapter="부칙", article="부칙 <제1호, 2025.12.01>", article_no=0,
                   article_sub=0, article_title="부칙", body=suppl_body,
                   is_supplementary=True),
    ]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.check_effective_date("정밀법", article="제2조", today=date(2026, 7, 12))
    t = r["transitional_provisions"]
    assert len(t) == 1
    assert "종전의 제2조" in t[0]["snippet"]


def test_effective_clause_fallback_single_provision(monkeypatch):
    arts = [
        ls.Article(law_type="법률", source="단순법", revision="시행 2026.01.01", file="f",
                   chapter="", article="제1조", article_no=1, article_sub=0,
                   article_title="목적", body="본문"),
        ls.Article(law_type="법률", source="단순법", revision="시행 2026.01.01", file="f",
                   chapter="부칙", article="부칙 <제2호, 2025.12.01>", article_no=0,
                   article_sub=0, article_title="부칙",
                   body="이 법은 공포 후 6개월이 경과한 날부터 시행한다.",
                   is_supplementary=True),
    ]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.check_effective_date("단순법", today=date(2026, 7, 12))
    assert "시행한다" in (r["latest_supplementary"]["effective_clause"] or "")


def test_transitional_hang_suffix_is_valid_mention(monkeypatch):
    # '제23조제1항'은 제23조의 유효한 언급 — 재현율 회복 (v1.3 최종리뷰 백로그)
    suppl_body = (
        "제1조(시행일) 이 법은 2026년 1월 1일부터 시행한다.\n"
        "제2조(경과조치) 이 법 시행 전 종전의 제23조제1항에 따른 처분은 유효하다.")
    arts = [
        ls.Article(law_type="법률", source="회복법", revision="시행 2026.01.01", file="f",
                   chapter="", article="제23조", article_no=23, article_sub=0,
                   article_title="해고 제한", body="본문"),
        ls.Article(law_type="법률", source="회복법", revision="시행 2026.01.01", file="f",
                   chapter="부칙", article="부칙 <제1호, 2025.12.01>", article_no=0,
                   article_sub=0, article_title="부칙", body=suppl_body,
                   is_supplementary=True),
    ]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.check_effective_date("회복법", article="제23조", today=date(2026, 7, 12))
    assert len(r["transitional_provisions"]) == 1
    assert "제23조제1항" in r["transitional_provisions"][0]["snippet"]
