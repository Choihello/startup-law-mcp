# HANDOFF — startup-law-mcp 세션 인수인계

> 새 세션에서 이 프로젝트를 이어받을 때 이 문서 하나로 재개할 수 있게 쓴 문서.
> 갱신일: 2026-07-14. 저장소: https://github.com/Choihello/startup-law-mcp

## 1. 지금 어디까지 왔나 (⚡ 재개 지점)

**로드맵 전부 완료 — v2.0 원격 배포까지 끝. 진행 중인 작업 없음.**

- 원격 서버: **https://startup-law-mcp.fly.dev/mcp** (도쿄 nrt, shared-cpu-1x 512MB, auto-stop 절전 — 유휴 후 첫 요청은 콜드스타트 수 초)
- 2026-07-14 배포 완료 기록: 앱 `startup-law-mcp` 생성(이름 충돌 없음) → `flyctl deploy --remote-only` 성공 → 원격 스모크 `SMOKE OK`(12도구·search_law 실응답) → `FLY_API_TOKEN` 시크릿 등록 → feat/v2.0 → main 병합·push → **fly-deploy 워크플로 런 성공 = 자동 재배포 검증 완료** → 재배포 후 스모크 재확인 `SMOKE OK`
- Fly 머신 **2대** 생성됨(Fly HA 기본값). 둘 다 auto-stop이라 과금 미미 — 1대로 줄이려면 `flyctl scale count 1`
- flyctl: `~/.fly/bin` (PATH에 없으면 수동 추가), 계정 zeratot@gmail.com
- **커넥터 등록(사용자)**: claude.ai 설정→커넥터에 위 URL 추가, 또는 `claude mcp add --transport http startup-law https://startup-law-mcp.fly.dev/mcp`

## 2. 프로젝트 한 줄 요약

창업 법령(50문서·8,191조문) + K-Startup 지원사업(공고 289·소개 511)을 조문 단위로
검색·조회·검증하는 MCP 서버. 도구 13개(원격판 12개). 포트폴리오 겸 실용 도구.
레퍼런스: koica-reg-mcp (구조·철학의 원형).

## 3. 버전 히스토리 (전부 main 병합·push 완료, CI 그린)

| 버전 | 내용 |
|---|---|
| v1.0 | 법령 5도구 (search/get/list/verify_citation/find_references) + 국가법령정보센터 동기화 |
| v1.1 | K-Startup 지원사업 4도구 (search/get/list_open/sync_programs) |
| v1.2 | 안정화: sync 방어(0건·급감70%·원자교체), 입력 검증(invalid_input·limit 1~50), ambiguous_source, data_status(10번째), CI(test.yml) |
| v1.3 | 창업 특화 3도구: delegation_map(위임 지도), startup_stage_guide(6단계 큐레이션+실재성 게이트), check_effective_date(시행일·경과조치) |
| v1.4 | 주간 자동 동기화 PR(weekly-sync.yml, 월 06시 KST) + 법령 전체 실패 가드(해외 IP 타임아웃 대응) + 경과조치 recall 회복 |
| v2.0 | Fly.io 원격 배포 — include_admin 게이트(원격 12/로컬 13), Dockerfile·fly.toml·fly-deploy.yml 자동 재배포, 원격 스모크. **배포 완료 2026-07-14 (§1)** |

## 4. 작업 방식 (이 프로젝트의 확립된 컨벤션)

1. **기능 단위 사이클**: superpowers:brainstorming(설계 질문→승인) → 스펙(docs/superpowers/specs/) → superpowers:writing-plans(전체 코드 포함 계획, docs/superpowers/plans/) → **superpowers:subagent-driven-development**로 실행
2. **SDD 실행 규칙**: feat/vX.Y 브랜치 · 태스크별 [구현 서브에이전트(계획 코드 verbatim이면 haiku, 판단 필요하면 sonnet) → 리뷰 서브에이전트(sonnet)] · Important 이상은 수정 서브에이전트→재리뷰 · 전 태스크 후 최종 브랜치 리뷰(opus) · 원장 `.superpowers/sdd/progress-v*.md`(로컬 전용, untracked)
3. **병합·push·자동 PR 머지는 항상 사용자 확인 후** (AskUserQuestion). 주간 자동 PR은 사용자가 "확인 후 머지해줘" 하면 diff 검증 후 머지
4. conventional commits + `Co-Authored-By: Claude` · 테스트 명령 `python -m pytest` · 표준 라이브러리만(의존성 mcp 하나) · NFC 정규화 · 키는 환경변수만(리터럴 커밋 금지 — 히스토리 grep으로 검증하는 관례)

## 5. 키·시크릿·설정 위치

- **LAW_OC** (국가법령정보센터): 값은 로컬 메모리 파일(§7)과 GitHub Actions Secrets에 있음
- **DATA_GO_KR_KEY** (공공데이터포털/K-Startup): 값은 로컬 메모리 파일(§7)과 GitHub Actions Secrets에 있음
- GitHub 저장소 설정 완료: Actions Secrets 2종, Workflow permissions(Read/write + PR 생성 허용)
- **FLY_API_TOKEN**: 등록 완료(2026-07-14) — Fly 배포 전용 토큰, fly-deploy.yml 자동 재배포용
- 원격 서버 자체는 시크릿 0개 (읽기 전용, 데이터는 이미지에 구움)

## 6. 알아둘 함정·백로그

- **law.go.kr은 GitHub 러너(해외 IP)에서 간헐 타임아웃** — weekly-sync의 법령 스텝은 continue-on-error, law_sync엔 전체 실패 가드(신규 성공 0건이면 매니페스트 무변경 raise). 부분 실패는 stale 플래그로 격리
- **자동 PR(GITHUB_TOKEN)은 test.yml CI를 트리거하지 않음** — 워크플로 내부 pytest가 게이트. main 브랜치 보호 걸면 교착 주의
- 백로그(우선순위 낮음): 항+호 복합 인용(제N조제M항제O호) 미매칭, 빈 큐레이션(laws:[]) 시 전체 prune 무signal, weekly-sync 인덱스 빌드 스텝 continue-on-error 미적용, .dockerignore 없음(빌드 컨텍스트 업로드만 느림), d_day 블록 DRY, 모듈 분리(v2 이후 재평가)

## 7. 문서 맵

- 스펙: `docs/superpowers/specs/` (v1.0·지원사업·v1.3·v1.4·v2.0 — 날짜순 5개)
- 계획: `docs/superpowers/plans/` (동일 5개 + v1.2 안정화)
- 감사 리포트: `docs/2026-07-12-보완-고도화-리포트.md` + `docs/2026-07-12-보완리포트-타당성분석.md` (외부 감사 → 검증·채택 과정)
- SDD 원장: `.superpowers/sdd/progress-v*.md` (로컬 전용)
- 세션 메모리: `~/.claude/projects/C--Users-zerat-OneDrive-------Teddy----MCP/memory/startup-law-mcp-project.md` — **키 값 포함, 최신 상태·백로그의 단일 진실**
- 스레드 마케팅 문구 초안: 세션 기록에 있음 (버전 A 창업자용/B 개발자용/C 3연작 — 도구 13개 기준으로 갱신 필요)

## 8. v2.0 이후 (지금 여기)

로드맵 완료. 남는 선택지: 스레드 배포 마케팅, 업종 특화(음식점·이커머스 인허가),
기업마당 소스 추가, BM25/평가셋(원격 사용량 생기면), Fly 머신 1대로 축소(`flyctl scale count 1`).
