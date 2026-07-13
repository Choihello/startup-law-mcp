# startup-law-mcp

![test](https://github.com/Choihello/startup-law-mcp/actions/workflows/test.yml/badge.svg)

**Claude에 URL 하나만 등록하면, 창업 법령 50개·8,191개 조문과 K-Startup 지원사업을 실제 원문을 근거로 답합니다.** LLM이 지어내는 "○○법 제N조" 환각 대신, 인덱스에서 대조한 진짜 조문만.

<!-- 데모 스크린샷 자리: claude.ai에서 실제 질문→조문 답변 화면을 캡처해
     docs/assets/demo.png 로 저장한 뒤 아래 줄의 주석을 해제하세요 -->
<!-- ![claude.ai에서 창업 세액감면 질문에 조세특례제한법 제6조 원문으로 답하는 데모](docs/assets/demo.png) -->

> **"카페 창업하는데 세액감면 받을 수 있어?"**
> → Claude가 `search_law` → `get_article`을 호출해 **조세특례제한법 제6조(창업중소기업 등에 대한 세액감면)** 원문·시행일(2026.01.01)을 근거로 답변합니다. 인용이 실재하는지 `verify_citation`으로 검증까지.

이 프로젝트가 유용했다면 ⭐ 하나가 큰 힘이 됩니다.

## 🚀 바로 쓰기 — 설치 불필요

원격 서버가 배포되어 있어 로컬 설치 없이 바로 연결할 수 있다: `https://startup-law-mcp.fly.dev/mcp`
(Fly.io 앱명은 배포 시 전역 유일성 확인 후 변경될 수 있다 — 실제 URL은 저장소 공지 참고).

| 클라이언트 | 등록 방법 |
|---|---|
| Claude Desktop / claude.ai | 설정 → 커넥터 → 커스텀 커넥터 → 위 URL 입력 |
| Claude Code | `claude mcp add --transport http startup-law https://startup-law-mcp.fly.dev/mcp` |

원격판은 관리 도구(`sync_programs`)를 제외한 **12개 도구**만 노출한다(데이터 갱신은 자동
재배포로 처리). 유휴 시 머신이 절전 상태로 내려가므로 첫 요청은 콜드스타트로 수 초 지연될
수 있다 — 이후 요청은 빠르다. 로컬에서 전체 13개 도구(관리 포함)로 직접 실행하려면
아래 "빠른 시작"을 따른다.

**창업 법령 + K-Startup 지원사업 통합 MCP** — 법인 설립, 세액감면, 첫 채용, 지식재산 등
창업 실무에서 부딪히는 핵심 법령을 조문 단위로 색인하고, K-Startup의 지원사업 공고·소개를
함께 조회해 Claude Desktop 같은 MCP 클라이언트에서 바로 인용 가능한 근거로 돌려준다.

## 무엇을 해결하나

- **범용 법령 검색의 한계**: 기존 법령 MCP는 국가법령정보센터 전체(수천 개 법령)를 얕게
  다루는 범용 검색이라, 창업 도메인 질문에 관련 없는 결과가 섞여 나오기 쉽다. 이 프로젝트는
  창업 관련 19개 법령(+ 시행령·시행규칙)만 큐레이션해 정확도를 높인다.
- **LLM의 조문 환각**: "○○법 제N조에 따르면…" 식으로 LLM이 실재하지 않는 조문을 인용하거나
  제목을 지어내는 문제를, 인덱스 대조로 잡아낸다(`verify_citation`).
- **조문 간 참조 추적**: "이 조문이 어디서 인용되는지", "이 조문은 어떤 다른 법을 인용하는지"를
  본법↔시행령↔타법 범위로 그래프화한다(`find_references`).
- **데이터 신선도**: 법령은 수시로 개정된다. 동기화 스크립트 1회 실행으로 국가법령정보센터
  Open API의 현행본을 그대로 반영한다.
- **지원사업 탐색**: "지금 신청 가능한 창업 지원사업이 뭐가 있는지"는 법령만으로는 알 수
  없다. K-Startup 조회서비스에서 사업공고·사업소개를 받아 모집 상태(open/closing_soon/
  upcoming/closed)와 D-day를 계산해 함께 제공한다(`search_program`, `list_open_programs`).

## 인덱싱 범위

큐레이션 19개 법률 + 하위 시행령·시행규칙, 총 **50개 문서 · 8,191개 조문** (2026-07-11 기준,
`data/sources.json` 실측치). 법령명·현행 여부는 매 동기화 시 Open API로 재확인한다.

| 분류 | 법률 | 문서 수(법률+시행령/규칙) | 조문 수 | 현재 시행일 |
|---|---|---:|---:|---|
| 창업·벤처 코어 | 중소기업창업 지원법 | 3 | 157 | 2026.07.01 |
| 창업·벤처 코어 | 벤처기업육성에 관한 특별법 | 3 | 429 | 2026.07.01 |
| 창업·벤처 코어 | 벤처투자 촉진에 관한 법률 | 3 | 219 | 2026.07.01 |
| 창업·벤처 코어 | 1인 창조기업 육성에 관한 법률 | 2 | 59 | 2026.03.31 |
| 창업·벤처 코어 | 중소기업기본법 | 2 | 137 | 2026.07.01 |
| 창업·벤처 코어 | 소상공인 보호 및 지원에 관한 법률 | 3 | 178 | 2026.07.01 |
| 창업·벤처 코어 | 중소기업 인력지원 특별법 | 2 | 185 | 2026.02.01 |
| 설립·운영 | 상법 | 2 | 1,295 | 2026.03.06 |
| 설립·운영 | 부가가치세법 | 3 | 400 | 2026.01.02 |
| 설립·운영 | 조세특례제한법 | 3 | 1,651 | 2026.01.01 |
| 고용 | 근로기준법 | 3 | 309 | 2025.10.23 |
| 고용 | 고용보험법 | 3 | 762 | 2026.05.12 |
| 고용 | 산업재해보상보험법 | 3 | 533 | 2026.07.01 |
| 지재·데이터 | 특허법 | 3 | 728 | 2025.11.11 |
| 지재·데이터 | 상표법 | 3 | 417 | 2025.11.11 |
| 지재·데이터 | 부정경쟁방지 및 영업비밀보호에 관한 법률 | 2 | 119 | 2025.10.01 |
| 지재·데이터 | 개인정보 보호법 | 2 | 306 | 2025.10.02 |
| 온라인 사업 | 전자상거래 등에서의 소비자보호에 관한 법률 | 3 | 204 | 2026.07.21 |
| 온라인 사업 | 약관의 규제에 관한 법률 | 2 | 103 | 2024.08.07 |

큐레이션 목록은 `data/laws.json`에서 관리한다.

### 지원사업 (K-Startup)

공공데이터포털 '창업진흥원_K-Startup 조회서비스'에서 받은 스냅샷 — **사업공고 309건**
(현행 모집 중·예정 건만 필터링 수집, 2026-07-12 기준) + **사업소개 511건**(전체 제도
카탈로그). `data/programs/*.json`에 저장되며, 공고는 모집기간·지원대상·상태·D-day를,
소개는 제도 개요·지원내용을 담는다. 아카이브 전체(약 2.9만 건)가 아니라 현재 유효한
공고만 유지하도록 조기 중단 수집한다 — 상세는 `sync_programs`/`program_sync.py` 참고.

## 빠른 시작

### 1. 요구 사항

- Python 3.10+ (표준 라이브러리 + `mcp` 패키지만 사용)
- 국가법령정보센터 Open API OC 키 — [open.law.go.kr](https://open.law.go.kr)에서 무료 발급
  (이메일 아이디 앞부분이 OC 값)
- (선택) 공공데이터포털 인증키 — 지원사업 조회를 쓰려면
  [data.go.kr](https://www.data.go.kr)에서 '창업진흥원_K-Startup 조회서비스' 활용신청 후
  발급되는 인증키(Decoding)가 필요하다. **법령 OC 키와는 완전히 별개의 키**이며 환경변수명도
  `DATA_GO_KR_KEY`로 다르다.

```bash
pip install -r requirements.txt
```

### 2. 법령 동기화 + 인덱스 빌드

```bash
# Windows (PowerShell)
$env:LAW_OC = "발급받은OC키"
python law_sync.py sync
python law_search.py build

# macOS/Linux
export LAW_OC=발급받은OC키
python law_sync.py sync
python law_search.py build
```

`law_sync.py sync`는 `data/laws.json` 큐레이션 목록을 Open API로 조회해
`data/laws/*.md`(법령별 마크다운)와 `data/sources.json`(매니페스트)을 갱신한다.
`law_search.py build`는 그 마크다운을 조문 단위로 파싱해 `data/index.json`
(검색용, 커밋 대상 아님)을 만든다.

### 3. 지원사업 동기화 (선택)

```bash
# Windows (PowerShell)
$env:DATA_GO_KR_KEY = "발급받은인증키"
python program_sync.py sync

# macOS/Linux
export DATA_GO_KR_KEY=발급받은인증키
python program_sync.py sync
```

`data/programs/announcements.json`(현행 공고)과 `data/programs/intros.json`(사업소개
전체)을 갱신한다. 저장소에는 초기 동기화 스냅샷이 이미 커밋되어 있으므로, 최신 공고가
필요할 때만 실행하면 된다(또는 MCP 클라이언트에서 `sync_programs` 도구 호출).

### 4. Claude Desktop 연결

`%APPDATA%\Claude\claude_desktop_config.json` (Windows) 또는
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)에 등록:

```json
{
  "mcpServers": {
    "startup-law": {
      "command": "python",
      "args": ["C:/절대/경로/startup-law-mcp/server.py"]
    }
  }
}
```

Claude Desktop을 완전히 재시작하면 도구 13개가 인식된다.

## 사용 예시

Claude Desktop에서 자연어로 물으면 서버가 알아서 검색→조회 도구를 호출한다.

- "창업기업 세액감면 요건 알려줘" → `search_law` + `get_article` → 조세특례제한법
  제6조(창업중소기업 등에 대한 세액감면) 근거로 답변
- "벤처기업 확인 요건이 뭐야" → 벤처기업육성에 관한 특별법 제25조(벤처기업의 해당
  여부에 대한 확인) 등 관련 조문
- "직원 첫 채용 때 근로계약서에 뭘 써야 해" → 근로기준법 제17조(근로조건의 명시)
- "이 문서에 인용된 조문들 실재하는지 검증해줘: …" → `verify_citation`으로
  ok / not_found / content_mismatch(제목 환각) / unknown_source 분류
- "중소기업창업 지원법 제2조를 인용한 다른 조문 찾아줘" → `find_references`로
  본법·시행령·타법 인용 그래프
- "예비창업자 지원사업 뭐 있어?" → `search_program`으로 사업소개+현재 공고를 함께 반환
  (예: 예비창업패키지, 창업기업(예비창업자)지원 등)
- "예비창업패키지 자격요건의 법적 근거는?" → `search_program`으로 지원대상·모집기간
  확인 + `search_law`로 중소기업창업 지원법의 창업자·예비창업자 정의 조문을 근거로
  통합 답변
- "중소기업창업 지원법의 시행령 위임 어디에 구체화됐어?" → `delegation_map`으로 본법
  조문이 위임한 대통령령 사항이 시행령·시행규칙 어느 조문에 구체화됐는지, 위임됐지만
  아직 안 만들어진 조문은 없는지(`sync_check`) 확인
- "법인 설립 단계에서 봐야 할 법령이랑 지원사업 알려줘" → `startup_stage_guide`로
  incorporation 단계 핵심 조문(상법 회사 성립, 부가가치세법 사업자등록 등)과 지금
  모집 중인 관련 지원사업을 함께 반환
- "전자상거래법 이 조항 지금 시행 중이야?" → `check_effective_date`로 시행/시행예정
  (D-day)/경과조치 여부를 판정 — 예: 전자상거래 등에서의 소비자보호에 관한 법률은
  2026.07.21 시행 예정으로 아직 시행 전

CLI로 직접 확인할 수도 있다:

```bash
python law_search.py search "창업 세액감면"
python law_search.py get 조세특례제한법 제6조
python law_search.py verify "조세특례제한법 제6조에 따라 창업중소기업은 세액감면을 받는다"
python law_search.py refs "중소기업창업 지원법" 제2조
```

## 도구 13개

> 입력 칸에서 `?`가 붙은 인자는 **선택**(생략 가능), 나머지는 필수입니다. `limit`은 모든
> 도구에서 1~50 범위의 정수만 허용합니다(벗어나면 `invalid_input` 반환). `law_type`은
> 인덱스의 실제 법종 값(법률·대통령령·총리령·고용노동부령 등)을 사용하며 `list_laws`로
> 확인할 수 있습니다.

법령 (5개):

| 도구 | 입력 | 반환 |
|---|---|---|
| `search_law` | `query, law_type?, source?, limit?, fuzzy?` | 조문 단위 검색 결과 (snippet + citation + score) |
| `get_article` | `source, article` | 조문 본문 전체 (시행일 포함) |
| `list_laws` | `law_type?` | 인덱싱된 법령 목록 + 시행일·조문 수 |
| `verify_citation` | `text` | 텍스트 내 "○○법 제N조" 인용을 ok / not_found / unknown_source / content_mismatch(제목 환각) / ambiguous_source(직전 문맥에 법령명 복수 후보)로 분류 |
| `find_references` | `source, article, limit?, include_mermaid?` | 대상 조문의 정방향·역방향 인용 그래프 (same_law/cross_law/external, Mermaid 옵션) |

지원사업 (4개, v1.1):

| 도구 | 입력 | 반환 |
|---|---|---|
| `search_program` | `query, status?, include_closed?, limit?` | 공고+사업소개 검색 결과 (status/d_day + snippet + score, 스냅샷 노후 warning) |
| `get_program` | `name` | 사업명 부분일치 상세 (사업소개·공고 전체 필드, 최대 5건) |
| `list_open_programs` | `limit?` | 모집 중·마감 임박·모집 예정 공고, 마감일 오름차순 (D-day 포함) |
| `sync_programs` | (없음) | K-Startup에서 공고·사업소개 재수집 → 스냅샷 교체 (`DATA_GO_KR_KEY` 필요, 재시작 불필요) |

기타 (1개, v1.2):

| 도구 | 입력 | 반환 |
|---|---|---|
| `data_status` | (없음) | 법령·지원사업 데이터 상태 — 조문/공고/소개 건수, 수집 시각(`fetched_at`), 신선도 경고, 동기화 오류(`sync_errors`)·정지된 법령(`stale_sources`) |

창업 특화 (3개, v1.3):

| 도구 | 입력 | 반환 |
|---|---|---|
| `delegation_map` | `source, article?` | 법률→시행령·시행규칙 위임 지도 — 대통령령 위임 조문이 하위 법령 어디에 구체화됐는지 정방향/역방향 연결, 위임됐지만 구체화되지 않은 조문을 `sync_check`로 표시 |
| `startup_stage_guide` | `stage?` | 창업 6단계(idea/incorporation/funding/hiring/tax/ip) 가이드 — 단계별 핵심 조문(실재성 검증 후 `missing` 표시)·체크리스트·현재 모집 중인 관련 지원사업. `stage` 생략 시 6단계 개요 |
| `check_effective_date` | `source, article?` | 법령·조문의 시행 상태 — 시행 중/시행 예정(D-day)/부칙 경과조치 판정 |

## 데이터 구조

```
data/
├── laws.json      # 큐레이션 목록 (법령명·분류) — 동기화 입력
├── sources.json    # 동기화 매니페스트 (법령명·법종·공포/시행일·소관부처·오류) — 커밋 대상
├── laws/           # 법령별 마크다운 "{법종}_{법령명}.md" — 커밋 대상
│   └── 법률_중소기업창업 지원법.md
├── index.json      # 검색용 조문 배열 (build 산출물, gitignored)
├── programs/       # K-Startup 지원사업 스냅샷 — 커밋 대상
│   ├── announcements.json  # 현행 사업공고 (fetched_at, count, items[])
│   └── intros.json         # 사업소개 전체 (fetched_at, count, items[])
├── stages.json     # 창업 6단계 큐레이션 (id/order/name/summary/key_articles/
│                   #   checklist/program_hints) — 커밋 대상. 조문 참조는 조회
│                   #   시점에 인덱스로 실재 검증하며(`tests/test_stages_data.py`
│                   #   게이트로 보증), 미존재 조문은 missing으로 정직 표시
└── _cache/         # probe 결과 원본 JSON (gitignored)
```

`server.py`(stdio, 로컬용 13개 도구)와 `server_http.py`(streamable-http, 원격 배포용
12개 도구·`sync_programs` 제외)는 같은 `register_tools()`를 공유하며 `data/`를 그대로
읽는다.

법령 마크다운은 "Format A" 고정 포맷을 따른다 (파서가 이 형식에 의존):

```markdown
# {법령명} ({법종} 제{공포번호}호, 시행 {시행일})

- 법종: {법종}
- 공포일자: ...
- 시행일자: ...
- 소관부처: ...

## {장 제목}

### 제{N}조({조문제목})

<시행 {조문시행일}>

{조문 본문 — 항·호·목 평탄화}

## 부칙 <제{공포번호}호, {공포일}>

{부칙 본문}
```

## 현행성 유지

법령은 수시로 개정되므로 주기적으로 재동기화가 필요하다.

```bash
python law_sync.py sync           # 전체 큐레이션 목록 재동기화
python law_sync.py sync --only 창업  # 이름에 "창업"이 포함된 법령만
python law_search.py build        # 마크다운 → 인덱스 재빌드 (동기화 후 항상 실행)
```

새 법령을 추가하려면 `data/laws.json`에 항목을 추가한 뒤 `sync` → `build`를 실행한다.
구조 확인이 필요하면 `python law_sync.py probe --query "법령명" --full`로 API 원본
JSON을 `data/_cache/`에 저장해 눈으로 대조할 수 있다.

지원사업 공고는 법령보다 훨씬 자주 바뀐다(마감·신규 공고가 매일 발생). 스냅샷은
`fetched_at`을 기록하며, `search_program`/`get_program`/`list_open_programs` 결과에
스냅샷이 **7일 이상** 지나면 `warning` 필드로 재동기화를 권고한다. 갱신은 CLI
(`python program_sync.py sync`) 또는 MCP 도구 `sync_programs` 호출 둘 다 가능하며,
후자는 서버 재시작 없이 바로 캐시를 무효화하고 최신 데이터를 반영한다. 공고 API는
2.9만 건 규모의 전체 아카이브를 반환하므로, `program_sync.py`는 페이지를 넘기며
모집중(`rcrt_prgs_yn == 'Y'`) 또는 마감일이 오늘 이후인 건만 남기고 2페이지 연속
해당 건이 없으면 조기 중단한다(현행 공고가 앞 페이지에 몰려 있는 API 정렬 특성 이용).

### 자동 동기화 (v1.4)

GitHub Actions 워크플로 `weekly-sync`는 **매주 월요일 아침 06:00 (KST)**에 법령·지원사업을 동기화한다. 변경이 감지되면 `auto/weekly-sync` 브랜치로 PR이 자동 생성되며, 리뷰 후 머지하면 `main`에 반영된다. 급감·스키마 이상이 감지되면 기존 데이터를 보존하고 PR 없이 워크플로가 실패한다. GitHub Actions 러너(해외 IP)에서는 국가법령정보센터가 타임아웃될 수 있어, 이 경우 법령 갱신은 건너뛰고(기존 데이터 보존) 지원사업 변경만 PR에 반영된다 — 법령 갱신은 로컬에서 `python law_sync.py sync` 실행을 권장.

**포크/자가 호스팅 설정**:
1. Repository Settings → Secrets and variables → Actions에서:
   - `LAW_OC`: 국가법령정보센터 Open API OC 키
   - `DATA_GO_KR_KEY`: 공공데이터포털 인증키 (지원사업 동기화 필요 시)
2. Settings → Actions → General에서:
   - Workflow permissions: "Read and write permissions" 선택
   - "Allow GitHub Actions to create and approve pull requests" 활성화
3. (선택) 수동 실행: Actions 탭 → weekly-sync → "Run workflow"

v1.0/v1.1 수동 실행은 여전히 가능하며, 자동 동기화는 변경이 있을 때만 PR을 생성한다.

**동기화 안전 정책**: `program_sync.py sync`(및 `sync_programs` 도구)는 API 응답을
그대로 덮어쓰지 않는다. 신규 0건(기존에 데이터가 있었는데 응답이 비어 있음), 기존
대비 70% 초과 감소(급감), JSON 스키마 이상 중 하나라도 감지되면 **기존 스냅샷을
그대로 보존하고 동기화를 중단**한다(예외로 실패를 알림, 절대 조용히 빈 데이터로
바꾸지 않음). 정상 응답도 임시 파일(`.tmp`)에 먼저 기록 → JSON 재파싱으로 유효성
검증 → `os.replace`로 원자 교체하는 순서를 거쳐, 쓰기 도중 프로세스가 죽어도 부분
기록된 파일이 남지 않는다. 결과에는 `announcements`/`intros` 각각 `before`/`after`/
`delta` 건수가 포함되어 어떤 변화가 있었는지 바로 확인할 수 있다.

**원격 서버 자동 재배포**: `main`에 `*.py`·`data/**`·`Dockerfile`·`fly.toml` 변경이
병합되면 `fly-deploy` 워크플로가 Fly.io 원격 빌더로 이미지를 재빌드해 배포한다. 즉
`weekly-sync` PR을 리뷰 후 머지하면 로컬 재실행 없이 원격 서버(`https://startup-law-mcp.fly.dev/mcp`)의
데이터도 자동으로 최신화된다.

## 기술 메모

- **의존성 최소화**: 검색·인덱싱·동기화 전 구간 표준 라이브러리만 사용(정규식·JSON·
  urllib). MCP 서버 부분만 `mcp` 패키지에 의존. 임베딩/시맨틱 검색은 채택하지
  않았다 — 의존성보다 조문 단위 키워드 검색의 정확도·투명성을 우선했다.
- **검색 알고리즘**: 한국어 조사 제거 토크나이저 + TF·IDF 가중 스코어링, 옵션으로
  음절 bi-gram 퍼지 매칭("세액감면 요건"을 "세액감면요건"으로 붙여 써도 잡는 부분
  매칭 류). 부칙 블록은 매우 긴 문서라 단순 등장
  횟수로 인해 짧고 정확한 본조보다 높은 점수를 받기 쉬웠는데, 부칙 점수에 ×0.2
  다운웨이트를 적용해 본칙이 우선 노출되도록 완화했다 — 그래도 정확한 법령명·
  조문번호를 알면 `get_article`을 직접 쓰는 편이 낫다.
- **인용 검증**: `verify_citation`은 "제N조" 패턴 앞 80자 내 최근접 법령명을 찾아
  귀속시키고, 괄호 안 제목이 실제 조문 제목의 부분(축약)이거나 음절 bi-gram
  Jaccard ≥ 0.4면 이표기로 인정, 그 외에는 `content_mismatch`(제목 환각 가능)로
  표시한다.
- **인용 그래프**: `find_references`는 "「법령명」 제N조" 형태의 외부 인용과
  법령명 생략된 동법 내부 인용("제N조")을 모두 파싱해 same_law/cross_law/external
  로 분류한다. 정확일치를 substring 매칭보다 우선해 "○○법"이 "○○법 시행령"으로
  오귀속되는 것을 방지한다.
- **오류 격리**: 동기화 중 개별 법령 조회 실패는 해당 법령만 `errors`에 기록하고
  전체 동기화를 중단하지 않는다.
- **지원사업 상태 계산**: 공고 API는 상태 필드를 직접 주지 않으므로, `apply_start`/
  `apply_end`와 오늘 날짜를 비교해 upcoming/open/closing_soon(마감 7일 이내)/closed/
  unknown(날짜 파싱 실패)을 서버에서 계산한다. 사업소개는 상시 정보라 상태·D-day가 없다.
- **컨테이너 이미지**: `Dockerfile`은 `data/`를 이미지에 그대로 복사한 뒤 빌드 시점에
  `python law_search.py build`로 `index.json`을 구워 넣는다 — 런타임 인덱스 빌드가
  없어 콜드스타트가 짧다.

## 로드맵

- **v1.0** — 큐레이션 19개 법률 인덱싱, 기본 5도구 + CLI, 로컬 stdio
- **v1.1** — K-Startup 지원사업 통합: `search_program`/`get_program`/
  `list_open_programs`/`sync_programs` 4도구 추가(총 9개), 공고 310건 + 사업소개
  511건 초기 동기화
- **v1.2 안정화 패치** — 동기화 방어 로직(0건·급감 70%·스키마 검증·원자 교체),
  URL 저장 경계 정규화, 매니페스트 인덱싱+stale 표시, 입력 검증(`invalid_input`,
  `limit` 1~50), `verify_citation`에 `ambiguous_source` 추가, `data_status` 도구(10개째),
  CI(pytest, Windows/Linux)
- **v1.3 창업 특화** — 3도구 추가(총 13개): `delegation_map`(법률→시행령·
  시행규칙 위임 조문 자동 연결 + 정비 점검), `startup_stage_guide`(창업 6단계별
  핵심 조문·체크리스트·관련 지원사업 큐레이션, `data/stages.json` + 조문 실재성
  게이트 테스트로 보증), `check_effective_date`(조문 시행일·경과규정 확인)
- **v1.4 자동 동기화** — GitHub Actions 주간 동기화(법령+지원사업) → 변경 감지 시 자동 PR
- **v2.0 원격 배포 (현재)** — `server_http.py`(streamable-http, 12개 도구) + Docker화 +
  Fly.io 배포(`fly.toml`, `fly-deploy` 워크플로) → 설치 없이 URL 하나로 연결, `main` 병합
  시 원격 서버 자동 재배포

## 라이선스

- **코드**: MIT.
- **법령 데이터**: 국가법령정보센터(law.go.kr) Open API를 통해 수집한 공공저작물로,
  저작권법 제24조의2(공공저작물의 자유이용)에 따라 이용한다.
- **지원사업 데이터**: 창업진흥원(K-Startup)이 공공데이터포털(data.go.kr)을 통해
  제공하는 '창업진흥원_K-Startup 조회서비스' 공공저작물을 이용한다.
- **면책**: 이 저장소의 법령 조문·지원사업 정보는 참조용이며, 법적 효력이 있는 공식
  조문은 반드시 [국가법령정보센터](https://www.law.go.kr)에서, 지원사업 신청 전에는
  반드시 [K-Startup](https://www.k-startup.go.kr) 원문 공고를 확인해야 한다. 본 서버는
  법률 자문을 제공하지 않으며, 지원사업 정보의 신청 가능 여부·마감일은 스냅샷 시점
  기준이므로 실제 신청 전 원문 확인이 필수다.
