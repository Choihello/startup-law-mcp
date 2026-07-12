# startup-law-mcp v1.4 설계 — 주간 자동 동기화 PR

- 작성일: 2026-07-13
- 상태: 사용자 승인 완료
- 선행: v1.3 (main ddde840, 도구 13개, pytest 125개, CI 그린)

## 목표

koica-reg-mcp의 주간 자동 동기화 패턴을 적용: 매주 법령+지원사업을 자동 동기화해
변경이 있으면 **자동 PR**을 올리고 사람이 검토·머지한다. "데이터 변경은 사람이 한 번
확인하고 반영"이 원칙. + v1.3 최종 리뷰 백로그(경과조치 재현율 회복) 수용.

## 확정 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| 범위·주기 | 법령+지원사업 통합, 주 1회 (일 21:00 UTC = 월 06:00 KST) + workflow_dispatch | 사용자 확정. 워크플로 1개로 단순, 수동 버튼 병행 |
| 반영 방식 | `auto/weekly-sync` 브랜치 → PR (직접 push 금지) | koica 철학 — 사람 검토 게이트 |
| PR 액션 | peter-evans/create-pull-request | 표준, 변경 없으면 PR 미생성 |
| 안전판 | v1.2 sync 방어(급감·빈 응답 → 워크플로 실패, PR 없음) + 동기화 후 전체 pytest | build로 인덱스가 생기므로 **stages 실재성 게이트가 실데이터로 실행** — 개정으로 사라진 큐레이션 조문을 PR 전에 탐지 |

## 구성

### 1. `.github/workflows/weekly-sync.yml`

schedule(cron `0 21 * * 0`) + workflow_dispatch. permissions: contents/pull-requests
write. 단계: checkout → Python 3.11 → 의존성 → `law_sync.py sync`+`law_search.py build`
(LAW_OC) → `program_sync.py sync`(DATA_GO_KR_KEY) → `pytest tests/ -q` → 동기화 로그
tail을 PR 본문으로 조립 → create-pull-request(add-paths: data/laws/**, data/sources.json,
data/programs/**). **run 스텝은 `set -o pipefail` 필수** (tee 파이프가 sync 실패를
가리지 않게). PYTHONUTF8=1.

### 2. 경과조치 재현율 회복 (백로그 수용)

`check_effective_date`의 label_re: `re.escape(label) + r"(?:제\d+항)*(?!(?:의|제)\d)"`
— "제N조제M항"은 그 조문의 유효 언급으로 허용, "제N조의M"(다른 조문)·"제N조제M호"
(보일러플레이트)는 계속 차단. 근로기준법 제23조 케이스가 회귀 테스트.

### 3. 저장소 설정 (E2E 시 적용)

- Actions Secrets: `LAW_OC`, `DATA_GO_KR_KEY` (gh secret set)
- Workflow permissions: Read and write + Allow Actions to create PRs (gh api)
- 병합·push 후 workflow_dispatch 1회 실행으로 E2E 검증

### 4. README

현행성 유지 섹션에 자동 동기화 문단(주기·PR 방식·시크릿 요건), 로드맵 v1.4 완료 표시.

## 범위 밖

Fly.io 원격 배포(v2.0), 동기화 실패 알림 채널(이슈 자동 생성 등 — Actions 기본
실패 메일로 충분), 지원사업 별도 주기.
