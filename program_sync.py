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


DRASTIC_DROP_RATIO = 0.7  # 기존 건수 대비 이 비율 초과 감소 시 동기화 거부 (정책값)


class SyncValidationError(RuntimeError):
    """응답·결과가 안전 기준 미달 — 기존 스냅샷을 보존하고 중단."""


def _validate_envelope(data, target: str) -> None:
    """응답 엔벨로프 스키마 검증 (probe 확정: totalCount/data[])."""
    if not isinstance(data, dict):
        raise SyncValidationError(f"{target}: 응답 최상위가 객체가 아님 ({type(data).__name__})")
    if not isinstance(data.get("data"), list):
        raise SyncValidationError(f"{target}: 'data'가 배열이 아님")
    tc = data.get("totalCount")
    ok = (isinstance(tc, int) and not isinstance(tc, bool) and tc >= 0) or \
         (isinstance(tc, str) and tc.isdigit())
    if not ok:
        raise SyncValidationError(f"{target}: 'totalCount'가 0 이상 정수가 아님 ({tc!r})")


def fetch_page(key: str, target: str, page: int = 1, per_page: int = 100) -> dict:
    """한 페이지 조회 + 엔벨로프 검증."""
    qs = urllib.parse.urlencode({
        "serviceKey": key, "page": page, "perPage": per_page, "returnType": "json",
    })
    data = _get_json(f"{API_BASE}/{ENDPOINTS[target]}?{qs}")
    _validate_envelope(data, target)
    return data


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


def fetch_all(key: str, target: str, per_page: int = 100, max_pages: int = 50) -> list[dict]:
    """전 페이지 수집 (사업소개용). totalCount 도달 또는 빈 배치에서 중단."""
    items: list[dict] = []
    page = 1
    while page <= max_pages:
        data = fetch_page(key, target, page=page, per_page=per_page)
        batch = data.get("data") or []
        if not batch:
            break
        items.extend(batch)
        total = int(data.get("totalCount") or 0)
        if total and len(items) >= total:
            break
        page += 1
    return items


def fetch_current_announcements(key: str, per_page: int = 100, max_pages: int = 50,
                                today: str | None = None) -> list[dict]:
    """현행 공고만 수집 — 공고 API는 전체 아카이브(2.9만+)를 반환하므로.

    기본 정렬이 모집중(Y) 우선인 점을 이용해, 페이지를 넘기며
    rcrt_prgs_yn=='Y' 또는 접수마감일이 오늘 이후인 아이템만 남기고
    '남긴 것 0건' 페이지가 2번 연속 나오면 중단한다.
    """
    from datetime import date

    today_s = today or date.today().isoformat()
    kept: list[dict] = []
    empty_streak = 0
    page = 1
    while page <= max_pages:
        data = fetch_page(key, "announcement", page=page, per_page=per_page)
        batch = data.get("data") or []
        if not batch:
            break
        cur = [r for r in batch
               if r.get("rcrt_prgs_yn") == "Y"
               or _date_norm(r.get("pbanc_rcpt_end_dt")) >= today_s]
        kept.extend(cur)
        empty_streak = 0 if cur else empty_streak + 1
        if empty_streak >= 2:
            break
        page += 1
    return kept


def _snapshot_count(fname: str) -> int | None:
    p = PROGRAMS_DIR / fname
    if not p.exists():
        return None
    try:
        return len(json.loads(p.read_text(encoding="utf-8")).get("items", []))
    except (json.JSONDecodeError, OSError):
        return None


def _guard_required_fields(label: str, items: list[dict], require_id: bool) -> None:
    """정규화 결과의 필수 필드 누락률이 10%를 넘으면 스키마 변경으로 간주."""
    if not items:
        return
    missing = sum(1 for it in items
                  if not it.get("name") or (require_id and not it.get("id")))
    if missing / len(items) > 0.10:
        raise SyncValidationError(
            f"{label}: 필수 필드 누락 {missing}/{len(items)}건 — API 스키마 변경 의심, 중단")


def _guard_counts(label: str, before: int | None, after: int) -> None:
    if after == 0 and (before or 0) > 0:
        raise SyncValidationError(f"{label}: 신규 0건 — 기존 {before}건 보존을 위해 중단")
    if before and after < before * (1 - DRASTIC_DROP_RATIO):
        raise SyncValidationError(
            f"{label}: 급감 감지 ({before} → {after}건) — 기준 "
            f"{int(DRASTIC_DROP_RATIO * 100)}% 초과 감소, 중단")


def _write_snapshot(fname: str, payload: dict) -> None:
    """임시 파일 기록 → JSON 재파싱 검증 → 원자 교체(os.replace)."""
    PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROGRAMS_DIR / (fname + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, PROGRAMS_DIR / fname)


def sync(key: str) -> dict:
    """현행 공고 + 사업소개 수집 → 안전 검증 통과 시에만 스냅샷 교체."""
    from datetime import datetime, timezone

    ann_raw = fetch_current_announcements(key)
    intro_raw = fetch_all(key, "intro")
    ann = [normalize_announcement(r) for r in ann_raw]
    intros = [normalize_intro(r) for r in intro_raw]

    if not ann and not intros:
        raise SyncValidationError("공고·사업소개 모두 0건 — 비정상 응답 의심, 중단")
    before_ann = _snapshot_count("announcements.json")
    before_intro = _snapshot_count("intros.json")
    _guard_required_fields("공고", ann, require_id=True)
    _guard_required_fields("사업소개", intros, require_id=False)
    _guard_counts("공고", before_ann, len(ann))
    _guard_counts("사업소개", before_intro, len(intros))

    fetched_at = datetime.now(timezone.utc).isoformat()
    for fname, items in (("announcements.json", ann), ("intros.json", intros)):
        _write_snapshot(fname, {"fetched_at": fetched_at, "count": len(items), "items": items})
    result = {
        "status": "ok",
        "fetched_at": fetched_at,
        "announcements": {"before": before_ann, "after": len(ann),
                          "delta": len(ann) - (before_ann or 0)},
        "intros": {"before": before_intro, "after": len(intros),
                   "delta": len(intros) - (before_intro or 0)},
    }
    print(f"동기화 완료: 공고 {len(ann)}건({result['announcements']['delta']:+d}), "
          f"사업소개 {len(intros)}건({result['intros']['delta']:+d})")
    return result


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


def cmd_sync(_args: argparse.Namespace) -> None:
    sync(_key())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("probe", help="API 원시 응답 확인")
    pp.add_argument("--target", choices=sorted(ENDPOINTS), required=True)
    pp.set_defaults(func=cmd_probe)
    ps = sub.add_parser("sync", help="공고·사업소개 전체 동기화")
    ps.set_defaults(func=cmd_sync)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
