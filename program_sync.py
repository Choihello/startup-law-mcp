"""K-Startup(창업진흥원) 지원사업 동기화 파이프라인.

공공데이터포털 'K-Startup 조회서비스'에서 사업공고·사업소개를 받아
data/programs/*.json 스냅샷으로 저장한다.

사용:
  set DATA_GO_KR_KEY=발급키(Decoding)     (Windows) / export DATA_GO_KR_KEY=... (POSIX)
  python program_sync.py probe --target announcement   # 원시 응답 구조 확인
  python program_sync.py probe --target intro
  python program_sync.py sync                           # 전체 동기화 (Task 3에서 추가)
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
PROGRAMS_DIR = DATA / "programs"
API_BASE = "https://apis.data.go.kr/B552735/kisedKstartupService01"
ENDPOINTS = {
    "announcement": "getAnnouncementInformation01",
    "intro": "getBusinessInformation01",
}


def _key() -> str:
    k = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not k:
        sys.exit("환경변수 DATA_GO_KR_KEY가 없습니다. data.go.kr에서 "
                 "'창업진흥원_K-Startup 조회서비스' 활용신청 후 인증키(Decoding)를 설정하세요.")
    return k


def _s(v) -> str:
    return str(v or "").strip()


def _date_norm(s) -> str:
    """'20260711'/'2026-07-11'/'2026.07.11' → '2026-07-11'. 그 외 ''."""
    s = str(s or "").strip()
    m = re.fullmatch(r"(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "startup-law-mcp/1.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # data.go.kr는 키 미승인·서비스 오류 시 HTTP 200 + XML 엔벨로프를 반환한다
        raise RuntimeError(f"JSON이 아닌 응답 (키 미승인/서비스 오류 가능): {body[:300]}")


def fetch_page(key: str, target: str, page: int = 1, per_page: int = 100) -> dict:
    """한 페이지 조회. 응답 엔벨로프는 probe로 확정 (기대: totalCount/data[])."""
    qs = urllib.parse.urlencode({
        "serviceKey": key, "page": page, "perPage": per_page, "returnType": "json",
    })
    return _get_json(f"{API_BASE}/{ENDPOINTS[target]}?{qs}")


def normalize_announcement(raw: dict) -> dict:
    """사업공고 원시 아이템 → 표준 레코드 (필드명: 2026-07-11 probe 확정)."""
    return {
        "id": _s(raw.get("pbanc_sn")),
        "kind": "공고",
        "name": _s(raw.get("biz_pbanc_nm") or raw.get("intg_pbanc_biz_nm")),
        "category": _s(raw.get("supt_biz_clsfc")),
        "summary": _s(raw.get("pbanc_ctnt")),
        "target": _s(raw.get("aply_trgt_ctnt") or raw.get("aply_trgt")),
        "target_age": _s(raw.get("biz_trgt_age")),
        "years": _s(raw.get("biz_enyy")),
        "region": _s(raw.get("supt_regin")),
        "apply_start": _date_norm(raw.get("pbanc_rcpt_bgng_dt")),
        "apply_end": _date_norm(raw.get("pbanc_rcpt_end_dt")),
        "org": _s(raw.get("pbanc_ntrp_nm") or raw.get("biz_prch_dprt_nm")),
        "contact": _s(raw.get("prch_cnpl_no")),
        "url": _s(raw.get("detl_pg_url") or raw.get("biz_gdnc_url")),
    }


def normalize_intro(raw: dict) -> dict:
    """사업소개 원시 아이템 → 표준 레코드 (필드명: 2026-07-11 probe 확정).

    소개에는 기관·연락처·지역 필드가 없어 빈 값. 소개글·특징·지원내용·예산은
    summary 한 필드에 줄바꿈으로 합쳐 보존한다.
    """
    parts = [_s(raw.get("supt_biz_intrd_info")), _s(raw.get("supt_biz_chrct")),
             _s(raw.get("biz_supt_ctnt")), _s(raw.get("biz_supt_bdgt_info"))]
    return {
        "id": _s(raw.get("id")),
        "kind": "사업소개",
        "name": _s(raw.get("supt_biz_titl_nm")),
        "category": _s(raw.get("biz_category_cd")),
        "summary": "\n".join(p for p in parts if p),
        "target": _s(raw.get("biz_supt_trgt_info")),
        "target_age": "",
        "years": "",
        "region": "",
        "apply_start": "",
        "apply_end": "",
        "org": "",
        "contact": "",
        "url": _s(raw.get("detl_pg_url")),
    }


def cmd_probe(args: argparse.Namespace) -> None:
    """원시 응답을 눈으로 확인 — 필드명·엔벨로프가 코드 가정과 다르면 여기서 발견."""
    key = _key()
    data = fetch_page(key, args.target, page=1, per_page=5)
    out = DATA / "_cache" / f"probe_programs_{args.target}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"엔벨로프 키: {sorted(data.keys())}")
    items = data.get("data") or []
    if items:
        print(f"아이템 수: {len(items)}")
        print("첫 아이템 필드/값:")
        for k, v in sorted(items[0].items()):
            print(f"  {k}: {str(v)[:80]}")
    print(f"원시 응답 저장: {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("probe", help="API 원시 응답 확인")
    pp.add_argument("--target", choices=sorted(ENDPOINTS), required=True)
    pp.set_defaults(func=cmd_probe)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
