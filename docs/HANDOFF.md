# HANDOFF — startup-law-mcp 세션 인수인계 (v3)

> 새 세션에서 **이 MCP 프로젝트만** 이어받을 때 이 문서 하나로 재개하는 문서.
> 갱신일: 2026-07-29. 저장소: https://github.com/Choihello/startup-law-mcp
> (다른 프로젝트(plan-lint-web 등)는 이 문서 범위 밖 — 각자 메모리·저장소 참조)

## 1. 현재 상태 (⚡ 재개 지점)

**v1.0~v2.1 로드맵 전부 완료·배포·운영 중. 열린 작업 없음.**
mcp 2.0.0 업그레이드는 2026-07-29 검증 결과 **불합격 → `mcp==1.28.1` 핀 유지**(§2.1).
다음 작업 후보 1순위는 §2-4 "배포 후 원격 스모크 자동화".

- 원격 서버: **https://startup-law-mcp.fly.dev/mcp** (도쿄 nrt, auto-stop 절전, 원격 13도구 / 로컬 14도구)
- 상담 스킬: 별도 저장소 https://github.com/Choihello/startup-consult (`match_programs` 기반 상담 양식)
- 자동화 현황: 주간 동기화(월 06시 KST) → **자동 머지·배포까지 이어짐** (c54a0c6에서 사람 검토 단계 제거 — sync 방어·실재성 게이트·pytest가 자동 게이트) + 주간 지표 스냅샷(월 06:30, docs/metrics/*.json)
- 최근 main: `c54a0c6` (주간 파이프라인 자동화 완결), 테스트 전부 그린

## 2. 🆕 MCP 2026-07-28 스펙 대응 검토 — v2.2 후보 (2026-07-29 조사)

어제(07-28) MCP 스펙 사상 최대 개정판이 확정됐다. 조사 근거: [공식 블로그](https://blog.modelcontextprotocol.io/posts/2026-07-28/), [The Register](https://www.theregister.com/devops/2026/07/23/model-context-protocol-prepares-to-break-with-its-stateful-past/5276722). 핵심 변경과 **우리 서버 영향 평가**:

### 스펙 변경 요약
- **무상태 코어**: initialize/initialized 핸드셰이크·`Mcp-Session-Id` 제거 — 요청이 `_meta`에 프로토콜 버전·클라이언트 정보를 자체 기술
- **헤더 라우팅**: `Mcp-Protocol-Version`/`Mcp-Method`/`Mcp-Name` HTTP 헤더 필수화 (게이트웨이가 JSON 파싱 없이 라우팅)
- **캐시 가능한 목록**: tools/list 등에 `ttlMs`·`cacheScope` — 정적 도구 목록이면 클라이언트 왕복 절감
- **MRTR**(다중 왕복 요청), 인가 강화(RFC 9207·CIMD), Tasks의 확장(extension) 이관, 공식 확장 프레임워크
- **Deprecated**(12개월 유예): 레거시 HTTP+SSE, Roots/Sampling/Logging, DCR. Feature Lifecycle 정책 도입 — **급하게 따라갈 필요 없음**

### 우리 서버 영향 (평가 결과)
| 항목 | 영향 |
|---|---|
| 무상태 코어 | **호재** — 이미 `stateless_http=True` + auto-stop 절전 설계라 방향 일치. 세션 제거는 콜드스타트 후 즉시 tool call 가능 = 우리 UX 개선 |
| 캐시 목록(ttlMs) | **채택 가치** — 도구 13개가 정적이라 긴 TTL 지정 이득 |
| deprecated 기능들 | **무영향** — SSE·Roots·Sampling·Logging·DCR 전부 미사용 |
| 인가 강화 | **무영향** — 무인증 공개 읽기 서버 |
| MRTR·Tasks | **불필요** — 짧은 읽기 도구뿐 |

### ⚠️ 실질 리스크 1건: SDK 버전 미고정 드리프트 → **해소됨 (2026-07-29)**
`requirements.txt`가 `mcp` 버전 미고정이라, 주간 자동 배포가 Docker 이미지를 재빌드할 때
최신 SDK가 무인으로 설치되는 상태였다. 조사 시점 **PyPI 최신은 이미 `2.0.0`**(메이저,
2026-07-28 스펙 대응)이고 운영본은 `1.28.1` — 다음 주간 배포에서 메이저 업그레이드가
사람 없이 들어갈 뻔했다. → `mcp==1.28.1`로 고정하고 실검증(전체 테스트 + 로컬 HTTP
스모크 13도구 `SMOKE OK`) 완료.

### v2.2 권장 작업 (착수 시 기존 사이클: 브레인스토밍→스펙→계획→SDD)
1. ~~**SDK 핀 고정**~~ — ✅ 2026-07-29 완료 (`mcp==1.28.1`)
2. ~~**mcp 2.0.0으로 의도적 업그레이드 검증**~~ — ❌ 2026-07-29 검증 완료, **핀 유지 결론**
   (`mcp==1.28.1`). 상세는 아래 §2.1
3. 신형 SDK가 노출하면: 도구 목록 `ttlMs` 지정, `server/discover` 검토
4. weekly-sync/fly-deploy에 **배포 후 원격 스모크 자동 실행** 스텝 추가 — 무인 배포의 사후 검증 (SDK 드리프트류 회귀를 자동 탐지; 자동 머지 체제에서 특히 중요)
5. ~~`fly-deploy.yml`의 `paths` 필터에 `requirements.txt` 추가~~ — ✅ 2026-07-29 완료.
   의존성만 바꾼 커밋도 재배포되므로, 위 2번(2.0.0 업그레이드)에서 핀만 올려도 원격에 반영된다

## 2.1 mcp 2.0.0 업그레이드 검증 결과 (2026-07-29) — **불합격, 핀 유지**

격리 venv(파이썬 3.12 + `mcp==2.0.0`)에서 검증. 저장소 코드는 무수정, `requirements.txt`는
`mcp==1.28.1` 그대로 둔다.

| 게이트 | 결과 |
|---|---|
| 전체 테스트(2.0.0, 코드 무수정) | ❌ **수집 단계에서 중단** — `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` |
| 로컬 remote_smoke(2.0.0, 코드 무수정) | ❌ `server_http.py` 자체가 부팅 불가 (동일 임포트 에러) |
| 원격 remote_smoke | ❌ 배포 불가 — 서버가 기동되지 않으므로 이미지 자체가 성립 안 됨 |
| claude.ai 커넥터 실연결 | ⏸ **미실행** — 2.0.0 배포본이 존재할 수 없어 실행 조건 미성립 |

**→ 4개 게이트 중 통과 0건. 사용자 기준("하나라도 실패하면 1.28.1 유지")에 따라 핀 유지.**

### 2.0.0의 파괴적 변경 (실측)
1. `mcp.server.fastmcp.FastMCP` **삭제** → `mcp.server.MCPServer`로 모듈·클래스 동시 개명
2. 생성자 kwargs `host`/`port`/`stateless_http` **제거** → `run()` /
   `run_streamable_http_async()` / `streamable_http_app()` 인자로 이동
3. `mcp.client.streamable_http.streamablehttp_client` **삭제** → 신 `mcp.Client(url)`
   (async 컨텍스트 매니저, `ClientSession` 수동 조립 불필요)
4. 의존성 교체: `httpx` → **`httpx2`**, `mcp-types`·`opentelemetry-api`·`pyjwt` 신규 유입
   (Requires-Python은 여전히 `>=3.10` — Dockerfile의 3.12-slim은 무영향)

### 마이그레이션 규모 측정 (스파이크)
개명 3건만 shim으로 가린 채 2.0.0에서 전체 테스트를 돌린 결과 **159/159 통과**.
즉 파손은 위 3개 지점에 국한되고 도구 정의·데코레이터·응답 스키마는 그대로 호환된다.
실제 수정 대상은 4파일뿐: `server.py`(임포트·타입힌트·생성자), `server_http.py`,
`tests/test_server.py`, `scripts/remote_smoke.py`.

### 프로토콜 호환성 (별개로 확인 — 둘 다 양호)
- **구버전 클라이언트 → 신버전 서버**: 1.28.1 클라이언트로 로컬 2.0.0 서버(shim 기동)
  스모크 → 13도구 + `search_law` 실호출 `SMOKE OK`. 커넥터 호환 우려는 근거 없음
- **신버전 클라이언트 → 운영 서버**: 2.0.0 클라이언트로 배포본(1.28.1) 스모크 →
  `SMOKE OK`, 프로토콜 `2025-11-25` 협상. **핀을 유지해도 신형 클라이언트가 끊기지 않는다**
- 참고: 2.0.0 ↔ 2.0.0은 `2026-07-28` 협상. 즉 파손은 순수 소스 API 레벨이며 와이어 레벨이 아님

### 결론 및 후속
- `mcp==1.28.1` 유지. 2.0.0은 **핀만 올리는 작업이 아니라 소스 마이그레이션**이므로
  §2-3(`ttlMs`)과 묶어 **v2.3 후보**로 이월. `MCPServer(cache_hints={...: CacheHint(ttl_ms, scope)})`가
  2.0.0에 이미 있으므로, 마이그레이션 시 캐시 목록 채택을 같이 처리하는 편이 이득
- 급하지 않은 근거 재확인: 신스펙 12개월 유예 + 운영본이 신형 클라이언트와도 정상 통신
- 기준선 재확인(1.28.1): 전체 테스트 **159 passed**, 원격 스모크 `SMOKE OK`

### 타이밍 기록 (왜 아슬아슬했나)
- 핀 직전 마지막 실배포: **Fly v7 = 2026-07-26 22:10 UTC** (주간 동기화 #3, 커밋 7198b1d)
  → 이 이미지는 2.0.0 업로드 이전이라 mcp **1.28.1**로 빌드됨
  (구 기록의 "마지막 실배포 2026-07-25(#2)"는 오기 — #3이 07-26에 자동 배포됨. 2026-07-29 정정)
- mcp 1.29.0 / 2.0.0 PyPI 업로드: **2026-07-28 13:41 / 13:45**
- 핀이 없었다면 **다음 주간 배포(월요일)의 이미지 재빌드에서 2.0.0이 무인 적용**될 뻔했다.
  핀은 그 직전에 들어갔다.
- **핀 반영 배포 완료: Fly v8 = 2026-07-29** (커밋 3990a62·37cadda). 즉 현재 프로덕션 이미지는
  `mcp==1.28.1` 명시 핀으로 **실제 재빌드된 것**이며, 이 v8에 대해 아래 §2.2 전수 점검을 통과했다.

## 2.2 운영 서버 상태 점검 (2026-07-29, Fly v8)

### 신스펙(2026-07-28) 반영 여부 — **미반영, 의도된 상태**
| 신스펙 항목 | 현재 |
|---|---|
| 프로토콜 버전 | ❌ `2025-11-25` 협상. 서버 지원 목록은 `2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25`. `MCP-Protocol-Version: 2026-07-28` 요청은 `-32600 Unsupported protocol version`으로 거절 |
| 무상태 코어 | ⭕ **행위 수준은 이미 충족** — `stateless_http=True`라 `Mcp-Session-Id` 미발급이고, initialize 없이 `tools/list` 단독 POST가 200으로 응답. 와이어 규격만 구스펙 |
| 캐시 목록(ttlMs·cacheScope) | ❌ 미노출 (`tool.meta` 없음). 2.0.0의 `cache_hints=`가 있어야 가능 → §2.1대로 v2.3 |
| Tasks / MRTR / 인가 강화 | — 미지원이나 **무영향** (capabilities에 `tasks=None`, 짧은 읽기 도구 + 무인증 공개 서버) |
| Deprecated(SSE·Roots·Sampling·Logging·DCR) | — 전부 미사용이라 무영향 |

→ 신스펙 미반영은 **정상**이다. 12개월 유예 + 신형(2.0.0) 클라이언트도 `2025-11-25`로 정상 협상되므로 기능 손실이 없다.

### 기능 이상 여부 — **이상 없음 (13/13)**
원격 13도구를 전부 실호출한 결과 **정상 13 / 실패 0**
(search_law·get_article·list_laws·verify_citation·find_references·search_program·
list_open_programs·get_program·match_programs·data_status·delegation_map·
startup_stage_guide·check_effective_date — 전부 에러 없이 실데이터 반환).
로컬 14도구 표면은 전체 테스트 **159 passed**로 커버.

### 데이터 신선도 — 정상
- 법령: 50문서 / **8,201조문** / `sync_errors: 0` (핸드오프 본문의 8,191은 동기화 #3 이전 수치)
- 지원사업: 공고 272 / 소개 511, 수집 `2026-07-26T22:09 UTC`(= 07-27 07:09 KST, 월요일 주간 동기화), `warnings: []`

## 3. 프로젝트 한 줄 요약

창업 법령(50문서·8,201조문 — 2026-07-29 기준, 주간 동기화로 증가) + K-Startup 지원사업(공고·소개)을 조문 단위로 검색·조회·
검증하고, 프로필 기반 자격 스크리닝(`match_programs`)까지 하는 MCP 서버.
로컬 14도구/원격 13도구. 레퍼런스: koica-reg-mcp.

## 4. 버전 히스토리 (전부 배포 완료)

| 버전 | 내용 |
|---|---|
| v1.0 | 법령 5도구 + 국가법령정보센터 동기화 |
| v1.1 | K-Startup 지원사업 4도구 |
| v1.2 | 안정화 (sync 방어·입력 검증·ambiguous_source·data_status·CI) |
| v1.3 | 창업 특화 3도구 (delegation_map·startup_stage_guide·check_effective_date) |
| v1.4 | 주간 자동 동기화 PR + 해외 IP 타임아웃 가드 |
| v2.0 | Fly.io 원격 배포 (2026-07-14) — 커넥터 URL, 자동 재배포, 도구 우선순위 패치 |
| v2.1 | 상담 스크리닝 (2026-07-15) — match_programs, 상담 스킬 별도 저장소 |
| (운영) | 주간 파이프라인 자동 머지·배포화(c54a0c6), 지표 스냅샷 워크플로 |

## 5. 작업 컨벤션

1. 기능 사이클: superpowers:brainstorming → 스펙(docs/superpowers/specs/) → writing-plans(전체 코드 포함) → **subagent-driven-development** (feat/vX.Y 브랜치, 태스크별 구현→리뷰 게이트, Important 이상 수정→재리뷰, 최종 브랜치 리뷰(opus), 원장 `.superpowers/sdd/progress-v*.md`)
2. **병합·push는 사용자 확인 후** — 단, 주간 데이터 PR은 자동 머지 체제로 전환됨(c54a0c6). 코드 변경은 여전히 사용자 확인
3. conventional commits · `python -m pytest` (현재 128+) · 표준 라이브러리(+mcp) · NFC · 키 리터럴 커밋 금지(히스토리 grep 검증 관례) · 문서만 커밋 시 `[skip ci]`

## 6. 키·시크릿

- 값 보관: **로컬 세션 메모리**(`~/.claude/projects/C--Users-zerat-OneDrive-------Teddy----MCP/memory/startup-law-mcp-project.md`) + GitHub Actions Secrets
- LAW_OC(법령), DATA_GO_KR_KEY(K-Startup), FLY_API_TOKEN(배포), FLY_METRICS_TOKEN(지표 readonly)
- METRICS_TOKEN(GitHub traffic용 fine-grained PAT)은 **미등록** — 사용자가 넣으면 주간 지표에 traffic 포함
- 원격 서버 자체는 시크릿 0개, flyctl `~/.fly/bin`, Fly 계정은 git author 이메일과 동일 (`flyctl auth whoami`로 확인)

## 7. 함정·백로그

- law.go.kr은 GH 러너(해외 IP)에서 간헐 타임아웃 — 전체 실패 가드 + stale 격리 + continue-on-error로 방어돼 있음
- 자동 PR(GITHUB_TOKEN)은 test.yml 미트리거 — 워크플로 내부 pytest가 게이트. **자동 머지 체제라 §2-4(배포 후 원격 스모크)가 더 중요해짐**
- Threads API 자동화는 Meta측 버그로 보류(수동 게시)
- 소소한 백로그: 항+호 복합 인용 미매칭, 빈 큐레이션 prune 무signal, .dockerignore 없음, region 1글자 쿼리 가드, needs_review 시간표현 노이즈, Fly 머신 1대 축소 옵션, d_day 블록 DRY, 모듈 분리 재평가

## 8. 문서 맵

- 스펙 6개: `docs/superpowers/specs/` · 계획 7개: `docs/superpowers/plans/`
- 감사 리포트 2개: `docs/2026-07-12-보완-*.md` · v2.1 구상 초안: `docs/2026-07-14-v2.1-상담에이전트-구상.md`(참고용)
- 지표: `docs/metrics/*.json` (주간 자동)
- SDD 원장: `.superpowers/sdd/progress-v*.md` (로컬 전용)

## 9. 다음 후보 (우선순위 제안)

1. **v2.2 — 배포 후 원격 스모크 자동화** (§2-4). 무인 자동 머지 체제의 사후 검증 공백이
   현재 남은 최대 리스크
2. **v2.3 — mcp 2.0.0 소스 마이그레이션 + `ttlMs`** (§2.1 — 4파일 개명 작업, 급하지 않음)
3. 마케팅 (스레드 후속 — v2.1 상담 각도, METRICS_TOKEN 등록하면 효과 측정 가능)
4. 업종 특화(음식점·이커머스 인허가) / 기업마당 소스 / BM25·평가셋(사용량 생기면)
