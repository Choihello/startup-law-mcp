# startup-law-mcp

한국 창업자를 위한 법령 조문 검색·조회·검증 MCP 서버 — 법인 설립, 세액감면, 첫 채용,
지식재산 등 창업 실무에서 부딪히는 핵심 법령을 조문 단위로 색인해 Claude Desktop 같은
MCP 클라이언트에서 바로 인용 가능한 근거로 돌려준다.

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

## 빠른 시작

### 1. 요구 사항

- Python 3.10+ (표준 라이브러리 + `mcp` 패키지만 사용)
- 국가법령정보센터 Open API OC 키 — [open.law.go.kr](https://open.law.go.kr)에서 무료 발급
  (이메일 아이디 앞부분이 OC 값)

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

### 3. Claude Desktop 연결

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

Claude Desktop을 완전히 재시작하면 도구 5개가 인식된다.

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

CLI로 직접 확인할 수도 있다:

```bash
python law_search.py search "창업 세액감면"
python law_search.py get 조세특례제한법 제6조
python law_search.py verify "조세특례제한법 제6조에 따라 창업중소기업은 세액감면을 받는다"
python law_search.py refs "중소기업창업 지원법" 제2조
```

## 도구 5개

| 도구 | 입력 | 반환 |
|---|---|---|
| `search_law` | `query, law_type?, source?, limit?, fuzzy?` | 조문 단위 검색 결과 (snippet + citation + score) |
| `get_article` | `source, article` | 조문 본문 전체 (시행일 포함) |
| `list_laws` | `law_type?` | 인덱싱된 법령 목록 + 시행일·조문 수 |
| `verify_citation` | `text` | 텍스트 내 "○○법 제N조" 인용을 ok / not_found / unknown_source / content_mismatch(제목 환각)로 분류 |
| `find_references` | `source, article, limit?, include_mermaid?` | 대상 조문의 정방향·역방향 인용 그래프 (same_law/cross_law/external, Mermaid 옵션) |

## 데이터 구조

```
data/
├── laws.json      # 큐레이션 목록 (법령명·분류) — 동기화 입력
├── sources.json    # 동기화 매니페스트 (법령명·법종·공포/시행일·소관부처·오류) — 커밋 대상
├── laws/           # 법령별 마크다운 "{법종}_{법령명}.md" — 커밋 대상
│   └── 법률_중소기업창업 지원법.md
├── index.json      # 검색용 조문 배열 (build 산출물, gitignored)
└── _cache/         # probe 결과 원본 JSON (gitignored)
```

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

v1.0은 수동 실행이 원칙이다(로드맵 v1.2에서 자동화 예정).

## 기술 메모

- **의존성 최소화**: 검색·인덱싱·동기화 전 구간 표준 라이브러리만 사용(정규식·JSON·
  urllib). MCP 서버 부분만 `mcp` 패키지에 의존. 임베딩/시맨틱 검색은 채택하지
  않았다 — 의존성보다 조문 단위 키워드 검색의 정확도·투명성을 우선했다.
- **검색 알고리즘**: 한국어 조사 제거 토크나이저 + TF·IDF 가중 스코어링, 옵션으로
  음절 bi-gram 퍼지 매칭("감면"↔"경감" 류). 알려진 한계: 부칙처럼 매우 긴 문서가
  단순 등장 횟수로 인해 짧고 정확한 본조보다 높은 점수를 받는 경우가 있다 — 정확한
  법령명·조문번호를 알면 `get_article`을 직접 쓰는 편이 낫다.
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

## 로드맵

- **v1.0** (현재) — 큐레이션 19개 법률 인덱싱, 기본 5도구 + CLI, 로컬 stdio
- **v1.1** — 창업 특화 3도구: `delegation_map`(법률→시행령·시행규칙 위임 조문 자동
  연결), `startup_stage_guide`(창업 단계별 관련 조문 큐레이션), `check_effective_date`
  (조문 시행일·경과규정 확인)
- **v1.2** — GitHub Actions 주간 동기화 → 변경 감지 시 자동 PR
- **v2.0** — 원격 배포 (streamable-http, URL 하나로 연결)

## 라이선스

- **코드**: MIT.
- **법령 데이터**: 국가법령정보센터(law.go.kr) Open API를 통해 수집한 공공저작물로,
  저작권법 제24조의2(공공저작물의 자유이용)에 따라 이용한다.
- **면책**: 이 저장소의 법령 조문은 참조용이며, 법적 효력이 있는 공식 조문은 반드시
  [국가법령정보센터](https://www.law.go.kr)에서 확인해야 한다. 본 서버는 법률
  자문을 제공하지 않는다.
