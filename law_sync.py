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


def _content_of(v) -> str:
    """'법종구분': {'content': '법률'} 또는 평문자열 양쪽 대응."""
    if isinstance(v, dict):
        return str(v.get("content", "")).strip()
    return str(v or "").strip()


def _jo_label(unit: dict) -> str:
    """조문단위 → '제2조' / '제2조의2'."""
    no = int(str(unit.get("조문번호", "0")).strip() or 0)
    label = f"제{no}조"
    sub = str(unit.get("조문가지번호", "") or "").strip()
    if sub and sub != "0":
        label += f"의{int(sub)}"
    return label


def _unit_text(unit: dict) -> str:
    """조문단위 하나의 본문을 항·호·목까지 평탄화 (줄바꿈 구분).

    실 API 응답은 항/호/목 내용이 평문자열일 때도 있고(단순 조문),
    다단 줄바꿈이 있는 목(예: 세율표처럼 가./나. 아래 1)/2) 소항목이 있는 경우)은
    문자열이 아니라 중첩 list로 온다. str()로 바로 감싸면 "['...', '...']" 같은
    파이썬 repr이 그대로 본문에 박히므로, 부칙내용과 동일하게 _flatten_text로
    문자열/리스트 양쪽을 재귀적으로 평탄화한다."""
    parts = [_flatten_text(unit.get("조문내용"))]
    for hang in _as_list(unit.get("항")):
        parts.append(_flatten_text(hang.get("항내용")))
        for ho in _as_list(hang.get("호")):
            parts.append(_flatten_text(ho.get("호내용")))
            for mok in _as_list(ho.get("목")):
                parts.append(_flatten_text(mok.get("목내용")))
    return "\n".join(p for p in parts if p)


def _flatten_text(v) -> str:
    """부칙내용 등 str/list 중첩 구조를 평탄화."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "\n".join(t for t in (_flatten_text(x) for x in v) if t)
    return str(v).strip()


def law_to_markdown(law_json: dict) -> tuple[str, dict]:
    """lawService.do JSON → (Format A 마크다운, 메타 dict)."""
    law = law_json.get("법령") or {}
    info = law.get("기본정보") or {}
    name = str(info.get("법령명_한글") or info.get("법령명한글") or "").strip()
    law_type = _content_of(info.get("법종구분")) or "법률"
    prom_no = str(info.get("공포번호", "")).strip()
    prom = _fmt_date(info.get("공포일자"))
    eff = _fmt_date(info.get("시행일자"))
    ministry = _content_of(info.get("소관부처"))

    lines = [
        f"# {name} ({law_type} 제{prom_no}호, 시행 {eff})",
        "",
        f"- 법종: {law_type}",
        f"- 공포일자: {prom}",
        f"- 시행일자: {eff}",
        f"- 소관부처: {ministry}",
        "",
    ]
    for unit in _as_list((law.get("조문") or {}).get("조문단위")):
        if str(unit.get("조문여부", "")).strip() != "조문":
            head = str(unit.get("조문내용", "") or "").strip()
            if head:
                lines += [f"## {head}", ""]
            continue
        title = str(unit.get("조문제목", "") or "").strip()
        head = f"### {_jo_label(unit)}({title})" if title else f"### {_jo_label(unit)}"
        lines += [head, ""]
        eff_jo = _fmt_date(unit.get("조문시행일자"))
        if eff_jo:
            lines += [f"<시행 {eff_jo}>", ""]
        body = _unit_text(unit)
        if body:
            lines += [body, ""]

    for buchik in _as_list((law.get("부칙") or {}).get("부칙단위")):
        b_no = str(buchik.get("부칙공포번호", "")).strip()
        b_date = _fmt_date(buchik.get("부칙공포일자"))
        text = _flatten_text(buchik.get("부칙내용"))
        lines += [f"## 부칙 <제{b_no}호, {b_date}>", ""]
        if text:
            lines += [text, ""]

    meta = {
        "name": name,
        "law_type": law_type,
        "law_id": str(info.get("법령ID", "")).strip(),
        "promulgation_no": prom_no,
        "promulgation_date": prom,
        "effective_date": eff,
        "ministry": ministry,
    }
    return "\n".join(lines).rstrip() + "\n", meta


def sync(oc: str, only: str | None = None) -> dict:
    """laws.json 큐레이션 목록 전체를 동기화. 법령 단위 오류 격리.

    갱신 실패 법령은 이전 매니페스트 엔트리를 stale로 유지해 검색에서 사라지지
    않게 하고, 큐레이션에서 제거된 법령의 md는 삭제(prune)한다.
    """
    curation = json.loads((DATA / "laws.json").read_text(encoding="utf-8"))
    LAWS_DIR.mkdir(parents=True, exist_ok=True)

    prev_by_name: dict[str, dict] = {}
    src_file = DATA / "sources.json"
    if src_file.exists():
        try:
            prev_by_name = {s.get("name"): s for s in
                            json.loads(src_file.read_text(encoding="utf-8")).get("sources", [])}
        except json.JSONDecodeError:
            prev_by_name = {}

    sources: list[dict] = []
    errors: list[dict] = []
    all_wanted: list[str] = []
    failed_reason: dict[str, str] = {}

    for entry in curation["laws"]:
        name = entry["name"]
        if only and only not in name:
            continue
        wanted = [name]
        if entry.get("include_subordinate", True):
            wanted += [f"{name} 시행령", f"{name} 시행규칙"]
        all_wanted.extend(wanted)
        try:
            hits = fetch_law_list(oc, name)
        except Exception as e:  # noqa: BLE001 — 법령 단위 격리
            errors.append({"law": name, "stage": "search", "error": str(e)})
            for w in wanted:
                failed_reason[w] = f"search: {e}"
            continue
        by_name = {str(h.get("법령명한글", "")).strip(): h for h in hits}
        for w in wanted:
            hit = by_name.get(w)
            if not hit:
                if w == name:
                    errors.append({"law": w, "stage": "match",
                                   "error": "법령 목록에서 정확일치 결과 없음"})
                    failed_reason[w] = "match: 목록에서 미발견"
                continue
            mst = str(hit.get("법령일련번호", "")).strip()
            try:
                md, meta = law_to_markdown(fetch_law(oc, mst))
                fname = f"{meta['law_type']}_{meta['name']}.md"
                (LAWS_DIR / fname).write_text(md, encoding="utf-8")
                meta.update({"file": fname, "mst": mst,
                             "group": entry.get("group", ""), "origin": "law.go.kr"})
                sources.append(meta)
                print(f"  ✓ {fname}")
            except Exception as e:  # noqa: BLE001
                errors.append({"law": w, "stage": "fetch", "error": str(e)})
                failed_reason[w] = f"fetch: {e}"

    # 전 항목 실패(해외 IP 차단·네트워크 장애·키 문제) — 매니페스트를 덮어쓰지 않고 보존.
    # 부분 실패는 아래 stale-carry로 격리하지만, 신규 성공이 0건이면 쓰기 자체를 중단한다.
    if not sources and errors:
        raise RuntimeError(
            f"법령 동기화 전체 실패 ({len(errors)}건) — 기존 매니페스트를 보존합니다. "
            f"첫 오류: {errors[0]['error']}")

    # 갱신 실패분: 이전 세대 엔트리를 stale로 유지 (파일이 남아 있는 경우만)
    fetched_names = {s["name"] for s in sources}
    for w in all_wanted:
        if w in fetched_names or w not in failed_reason:
            continue
        p = prev_by_name.get(w)
        if p and (LAWS_DIR / p.get("file", "")).exists():
            stale = dict(p)
            stale["stale"] = True
            stale["stale_reason"] = failed_reason[w]
            sources.append(stale)

    manifest = {"count": len(sources), "sources": sources, "errors": errors}
    src_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    # 고아 파일 정리 — 새 매니페스트(stale 포함)에 없는 md 삭제
    if only is None:
        valid_files = {s.get("file") for s in sources}
        removed = []
        for p in LAWS_DIR.glob("*.md"):
            if p.name not in valid_files:
                p.unlink()
                removed.append(p.name)
        if removed:
            print(f"고아 파일 {len(removed)}개 제거: {', '.join(removed[:5])}")
    print(f"동기화 완료: {len(sources)}개 문서(스테일 {sum(1 for s in sources if s.get('stale'))}건 포함), "
          f"오류 {len(errors)}건")
    return manifest


def cmd_sync(args: argparse.Namespace) -> None:
    sync(_oc(), only=args.only)


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
    ps = sub.add_parser("sync", help="laws.json 전체 동기화")
    ps.add_argument("--only", default=None, help="법령명 부분일치 필터")
    ps.set_defaults(func=cmd_sync)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
