# startup-law-mcp v1.1 설계 — 지원사업(K-Startup) 통합

- 작성일: 2026-07-11
- 상태: 사용자 승인 완료
- 선행: v1.0 (법령 5도구, 50문서/8,191조문) 완성·공개 — github.com/Choihello/startup-law-mcp

## 배경과 목표

창업자가 실제로 매일 찾는 정보는 법령보다 지원사업(예비창업패키지, 초기창업패키지,
TIPS 등)이다 — 사용자가 이를 도메인 핵심으로 확인. v1.1은 K-Startup(창업진흥원)
지원사업 데이터를 기존 법령 축과 나란히 통합해, 한 서버에서 "지원사업 탐색 +
자격요건의 법적 근거"를 함께 답하는 창업 도우미로 확장한다.

**성공 기준**
- "예비창업자 대상 지원사업 뭐 있어?" → 모집 중 공고가 마감일·지원대상과 함께 반환
- "예비창업패키지가 뭔데, 지금 신청 되나?" → 사업소개(제도) + 현재 공고 상태 통합 답변
- 마감 지난 공고가 기본 검색을 오염시키지 않음
- 스냅샷이 오래되면 결과에 갱신 권장 경고가 자동 동봉

## 확정 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| 데이터 성격 | 사업소개(정적 제도 설명) + 현재 공고(동적) | 제도 질문과 모집 질문 모두 커버 |
| 소스 | K-Startup(창업진흥원) 단일 | 창업 특화·노이즈 없음·파이프라인 1개. 기업마당은 후순위 |
| 현행성 | git 스냅샷 + `sync_programs` 온디맨드 갱신 | 법령과 동일 패턴, 오프라인 동작, API 장애 격리 |
| 통합 형태 | 기존 서버에 지원사업 축 추가 (단일 인덱스 통합·별도 서버 기각) | 조문 모델과 공고 모델은 구조가 다름; 포폴 스토리는 통합 서버 |
| 버전 | v1.1 (특화 3도구는 v1.2로 밀림) | 사용자가 지원사업을 도메인 핵심으로 우선함 |

## 범위

### v1.1 포함
- `program_sync.py` — K-Startup 사업공고·사업소개 수집 → `data/programs/*.json` 스냅샷
- `programs.py` — 로드·상태 계산·검색·조회 (law_search의 tokenize/make_snippet 재사용)
- MCP 도구 4개 추가: `search_program` / `get_program` / `list_open_programs` / `sync_programs`
- SERVER_INSTRUCTIONS 갱신 — 법령+지원사업 통합 안내
- README 갱신 + 로드맵 재편 (v1.2 특화 3도구, v1.3 Actions, v2.0 원격)

### v1.1 제외
- 기업마당(bizinfo) 소스 — 커버리지 필요 시 후속
- 공고 아카이브(종료 공고 축적) — 스냅샷은 현행만
- 지원사업↔법령 수작업 매핑(related_laws) — YAGNI, instructions 수준 연계로 충분
- 지역·연령 등 구조화 필터 고도화 — 검색어로 커버, 실사용 후 판단

## 데이터 소스

**공공데이터포털 "창업진흥원_K-Startup(사업소개,사업공고,콘텐츠 등)_조회서비스"**
(data.go.kr/data/15125364/openapi.do)
- 사업공고 조회: 사업명·유형·개요·지원대상·모집기간·신청방법·문의처·상세URL
- 사업소개 조회: 제도 단위 소개(예비창업패키지 등)·지원내용
- 인증키: data.go.kr 발급 (무료·자동승인), 환경변수 `DATA_GO_KR_KEY`로만 주입
- **실제 응답 필드명·엔벨로프는 구현 첫 태스크에서 probe로 확정** (v1.0의 교훈:
  probe를 뒤로 미루지 않고 맨 앞에 둔다)

## 아키텍처

```
program_sync.py     # 수집: fetch(페이지네이션) → normalize → data/programs/*.json + fetched_at
programs.py         # 조회: load(캐시) → status 계산 → search/get/list + stale 경고
server.py           # 도구 4개 추가 (register_tools 확장), SERVER_INSTRUCTIONS 갱신
data/programs/
├── announcements.json   # {"fetched_at": ISO, "count": n, "items": [정규화 레코드]}
└── intros.json          # 동일 구조
```

### 정규화 레코드 (내부 스키마 — API 필드명 변화로부터 절연)

```json
{
  "id": "...", "kind": "공고"|"사업소개", "name": "...", "category": "...",
  "summary": "...", "target": "...", "target_age": "...", "years": "...",
  "region": "...", "apply_start": "YYYY-MM-DD", "apply_end": "YYYY-MM-DD",
  "org": "...", "contact": "...", "url": "..."
}
```

사업소개는 apply_* 가 빈 값일 수 있다 (제도 설명이므로).

### 공고 상태 계산 (조회 시점, 저장 안 함)

- `upcoming` — 오늘 < 접수시작
- `open` — 접수기간 내, 마감까지 8일 이상
- `closing_soon` — 접수기간 내, 마감까지 7일 이내
- `closed` — 오늘 > 접수마감
- `unknown` — 접수기간 파싱 불가

검색·목록의 기본 동작은 `closed` 제외 (`include_closed=True`로 포함).
모든 상태 계산 함수는 `today` 파라미터 주입 가능 (테스트 고정용).

### 검색

- `law_search.tokenize`·`make_snippet` 재사용. IDF는 미적용 — 공고 코퍼스는 수백 건
  규모라 TF + 사업명 매칭 가중(×5)으로 충분 (YAGNI).
- 검색 대상 텍스트: name + category + summary + target + region + org 연결.

### 신선도 경고

`fetched_at`이 7일 이상 경과하면 검색·목록 결과에 warning 필드 동봉:
"지원사업 스냅샷이 N일 지났습니다. sync_programs로 갱신을 권장합니다."
데이터 파일이 없으면 명확한 안내와 함께 빈 결과.

## MCP 도구 4개

| 도구 | 입력 | 반환 |
|---|---|---|
| `search_program` | `query, status?, include_closed?, limit?` | 공고+사업소개 검색 결과 (status·d_day·snippet·url) + warning |
| `get_program` | `name` | 이름 부분일치 상세 (전체 필드, 공고는 status·d_day 포함, 최대 5건) |
| `list_open_programs` | `limit?` | 모집 중·마감 임박·예정 공고, 마감일 오름차순, d_day 포함 |
| `sync_programs` | — | K-Startup 재수집 → 스냅샷 갱신 → 캐시 무효화 (재시작 불필요). DATA_GO_KR_KEY 필요 |

`SERVER_INSTRUCTIONS` 갱신: 지원사업·공고·모집 질문 → `search_program`/`list_open_programs`
먼저; 자격요건·법적 근거 질문 → `search_law` 병행; 두 축을 합친 통합 답변이 이 서버의 정체성.

## 오류 처리

- API 실패(키 오류·네트워크): sync는 명확한 메시지로 실패, 기존 스냅샷은 보존 (부분 덮어쓰기 금지 — 전체 성공 시에만 파일 교체)
- 페이지네이션: totalCount 기반 반복, 빈 배치 시 중단, max_pages 상한
- 날짜 파싱 실패: 해당 공고 status=unknown, 검색에는 포함
- 인증키 미설정: sync_programs가 발급 안내 메시지 반환 (조회 도구는 스냅샷으로 정상 동작)

## 테스트 전략

- fixture: 가짜 공고 4건(open/closing_soon/upcoming/closed 각 1) + 사업소개 2건, `today=date(2026, 7, 11)` 고정 주입
- 단위: 상태 계산 경계(마감 당일·7일 경계), 마감 필터, 검색 랭킹(사업명 가중), stale 경고, 정규화(실 probe 응답 기반 fixture)
- 서버: 도구 9개 등록 검증
- E2E: 실키 sync → CLI 스모크 ("예비창업패키지" 검색·상세·모집 중 목록)

## 사용자 사전 준비물

data.go.kr 회원가입 → "창업진흥원_K-Startup 조회서비스" 활용신청 → 일반 인증키(Decoding).
환경변수 `DATA_GO_KR_KEY`. 법령 OC 키와 별개.

## 라이선스·고지

데이터 출처 고지에 창업진흥원(K-Startup)·공공데이터포털 추가. 공고는 참조용이며
신청 전 원문 공고(k-startup.go.kr) 확인 면책 문구.
