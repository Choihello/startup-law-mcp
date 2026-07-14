"""저장소·원격 서버 사용 지표 스냅샷 — docs/metrics/YYYY-MM-DD.json 생성.

GitHub Traffic API는 14일치만 보관하므로 주기 수집으로 이력을 보존한다.
개별 수집 실패(권한·네트워크)는 스냅샷에 error로 기록하고 전체는 성공시킨다.

사용:  python -X utf8 scripts/collect_metrics.py
환경변수:
  METRICS_TOKEN | GITHUB_TOKEN — GitHub API 토큰.
      traffic(views/clones)은 저장소 관리자 권한 토큰 필요 — Actions 기본
      GITHUB_TOKEN엔 administration 권한이 없어 403이 나며, 이 경우
      stars/forks만 기록된다. 전체 수집엔 fine-grained PAT(METRICS_TOKEN).
  FLY_API_TOKEN (선택) — Fly Prometheus에서 최근 7일 HTTP 응답 수 집계.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = os.environ.get("METRICS_REPO", "Choihello/startup-law-mcp")
FLY_APP = os.environ.get("FLY_APP", "startup-law-mcp")
FLY_ORG = os.environ.get("FLY_ORG", "personal")
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "metrics"


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _try(fn):
    """(결과, 오류문자열) 쌍 반환 — 실패해도 스냅샷 전체를 죽이지 않는다."""
    try:
        return fn(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def collect_github(token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "User-Agent": "startup-law-mcp-metrics"}
    base = f"https://api.github.com/repos/{REPO}"
    out: dict = {}
    repo, err = _try(lambda: _get(base, headers))
    if repo is None:
        out["error"] = err
        return out
    out["stars"] = repo.get("stargazers_count")
    out["forks"] = repo.get("forks_count")
    out["watchers"] = repo.get("subscribers_count")
    for key, path in (("views", "traffic/views"), ("clones", "traffic/clones")):
        data, err = _try(lambda p=path: _get(f"{base}/{p}", headers))
        out[key] = data if data is not None else {"error": err}
    return out


def parse_fly_result(data: dict) -> dict:
    """Prometheus 응답에서 스칼라 하나를 꺼낸다 — 실패 시 원본 보존."""
    try:
        value = data["data"]["result"][0]["value"][1]
        return {"http_responses_7d": round(float(value))}
    except (KeyError, IndexError, TypeError, ValueError):
        return {"raw": data, "note": "쿼리 결과 해석 실패 — 원본 보존"}


def fly_auth_header(token: str) -> str:
    """매커룬 토큰(fm...)은 FlyV1 스킴, 그 외는 Bearer.

    `flyctl tokens create deploy` 출력은 "FlyV1 fm2_..." 형태로 접두사를
    이미 포함하기도 한다 — 그대로 통과시킨다.
    """
    token = token.strip()
    if token.startswith("FlyV1 "):
        return token
    if token.startswith("fm"):
        return f"FlyV1 {token}"
    return f"Bearer {token}"


def collect_fly(token: str) -> dict:
    query = (f'sum(increase(fly_app_http_responses_count'
             f'{{app="{FLY_APP}"}}[7d]))')
    url = (f"https://api.fly.io/prometheus/{FLY_ORG}/api/v1/query?"
           + urllib.parse.urlencode({"query": query}))
    data, err = _try(
        lambda: _get(url, {"Authorization": fly_auth_header(token)}))
    if data is None:
        return {"error": err}
    return parse_fly_result(data)


def build_snapshot(github: dict, fly: dict) -> dict:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": REPO,
        "github": github,
        "fly": fly,
    }


def main() -> int:
    gh_token = os.environ.get("METRICS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        print("METRICS_TOKEN 또는 GITHUB_TOKEN 환경변수가 필요합니다",
              file=sys.stderr)
        return 1
    fly_token = os.environ.get("FLY_API_TOKEN")
    snapshot = build_snapshot(
        collect_github(gh_token),
        collect_fly(fly_token) if fly_token else {"skipped": "FLY_API_TOKEN 없음"})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / (datetime.now(timezone.utc).strftime("%Y-%m-%d")
                          + ".json")
    out_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    gh = snapshot["github"]
    views = gh.get("views") or {}
    clones = gh.get("clones") or {}
    print(f"saved {out_path.name} — stars {gh.get('stars')}, "
          f"views14d {views.get('count')}, clones14d {clones.get('count')}, "
          f"fly {snapshot['fly']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
