"""국가법령정보센터 Open API 동기화 파이프라인.

data/laws.json(큐레이션 목록)의 법령을 open.law.go.kr API로 받아
Format A 마크다운(data/laws/*.md)과 매니페스트(data/sources.json)로 저장한다.

사용:
  set LAW_OC=발급받은키          (Windows) / export LAW_OC=... (POSIX)
  python law_sync.py probe --query "중소기업창업 지원법"   # API 응답 원본 확인
  python law_sync.py sync                                  # 전체 동기화
  python law_sync.py sync --only 창업                      # 이름 부분일치만
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LAWS_DIR = DATA / "laws"
API_BASE = "https://www.law.go.kr/DRF"


def _oc() -> str:
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        sys.exit("환경변수 LAW_OC가 없습니다. open.law.go.kr에서 OC 키를 발급받아 설정하세요.")
    return oc


def _as_list(v) -> list:
    """API 응답의 dict-or-list 정규화. 단건은 list로 안 감싸져 온다."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _fmt_date(s) -> str:
    """'20260101' → '2026.01.01'. 이미 포맷됐거나 빈 값은 그대로/빈 문자열."""
    s = str(s or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}.{s[4:6]}.{s[6:]}"
    return s


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "startup-law-mcp/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_law_list(oc: str, query: str) -> list[dict]:
    """법령 목록 검색(현행). 각 항목: 법령명한글·법령일련번호(MST)·법령ID·시행일자 등."""
    q = urllib.parse.quote(query)
    url = f"{API_BASE}/lawSearch.do?OC={oc}&target=law&type=JSON&display=100&query={q}"
    data = _get_json(url)
    return _as_list((data.get("LawSearch") or {}).get("law"))


def fetch_law(oc: str, mst: str) -> dict:
    """법령 본문 조회. 반환 최상위 키: '법령' → 기본정보/조문/부칙."""
    url = f"{API_BASE}/lawService.do?OC={oc}&target=law&type=JSON&MST={mst}"
    return _get_json(url)


def cmd_probe(args: argparse.Namespace) -> None:
    """API 응답 원본을 눈으로 확인 — 실제 JSON 구조가 fixture와 다르면 여기서 발견한다."""
    oc = _oc()
    hits = fetch_law_list(oc, args.query)
    print(json.dumps(hits[:3], ensure_ascii=False, indent=1))
    if hits and args.full:
        mst = str(hits[0].get("법령일련번호", ""))
        law = fetch_law(oc, mst)
        out = DATA / "_cache" / f"probe_{mst}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(law, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"본문 JSON 저장: {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("probe", help="API 응답 원본 확인")
    pp.add_argument("--query", required=True)
    pp.add_argument("--full", action="store_true", help="첫 결과의 본문 JSON까지 저장")
    pp.set_defaults(func=cmd_probe)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
