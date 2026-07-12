# startup-law-mcp v1.3 설계 — 창업 특화 3도구

- 작성일: 2026-07-12
- 상태: 사용자 승인 완료
- 선행: v1.2 안정화 패치 (main cf30f5b, pytest 105개, 도구 10개, CI 그린)

## 배경과 목표

v1.0 스펙에서 예고한 창업 특화 3도구를 구현한다 — 범용 법령 검색과의 차별화 핵심.
"이 법률 조문의 시행령 위임이 어디로 갔는지", "창업 단계별로 뭘 봐야 하는지",
"이 조항이 지금 시행 중인지"는 기존 검색 도구로는 여러 번 오가야 답할 수 있는
질문들이다. 도구 10 → 13개.

**성공 기준**
- "중소기업창업 지원법 제2조의 대통령령 위임이 시행령 어디에 구체화됐나" → 위임 엣지 반환
- "법인 설립 단계에서 봐야 할 법령이랑 지금 신청 가능한 지원사업 알려줘" → 큐레이션 조문 + 모집 중 공고 통합 반환
- "전자상거래법 이 조항 지금 시행 중이야?" → 시행일·상태·경과조치 반환
- 큐레이션(stages.json)의 모든 조문 참조가 인덱스에 실재함을 테스트가 상시 보증

## 실데이터 근거 (2026-07-12 확인)

- 법률 19개에 `대통령령으로 정한*` 위임 문구 543개
- 시행령은 모법을 전체 이름이 아니라 **"법 제N조"로 지칭** (중기창업법 시행령 기준
  99곳 vs 전체 이름 인용 62곳) — 제1조 부근 `(이하 "법"이라 한다)` 정의 관행
- 시행규칙은 "법"(모법)·"영"(시행령) 두 축약을 함께 사용
- 부칙에 시행일 조문(제1조(시행일))과 조문 번호를 명시한 경과조치가 구조적으로 존재

## 확정 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| 위임 연결 방식 | 조회 시점 실시간 스캔 (인덱스 스키마 불변) | 조회 빈도 낮음, 빌드 복잡도 회피 (사전 계산·인덱스 확장 기각) |
| 모법 해석 | 이름 규칙: `{source} 시행령`/`시행규칙` ↔ 모법 | 실데이터에서 100% 성립하는 한국 법령 명명 관행 |
| stage guide 구성 | 6단계 + 지원사업 연계 | 사용자 확정 (2026-07-12) |
| stage 로직 위치 | 신규 소형 모듈 `stages.py` | 법령(law_search)·지원사업(programs) 양쪽을 조합하는 책임 — 707줄 law_search에 얹지 않음 |
| 큐레이션 품질 | stages.json의 모든 조문 참조 실재성을 pytest 상시 검증 | 환각 큐레이션 원천 차단 |
| guide의 지원사업 연계 | program_hints 검색어를 조회 시점에 실행해 모집 중 상위 3건 동봉 | 정적 공고 ID 저장은 마감과 함께 썩음 — live 검색이 항상 현행 |

## 도구 설계

### 1. `delegation_map(source: str, article: Optional[str] = None) -> dict`

위치: `law_search.py`. koica `compliance_radar`의 법령판 + 위임 엣지 연결.

- **위임 문구 패턴**: `대통령령으로 정한*`, `총리령으로 정한*`, `(고용노동부령|중소벤처기업부령|…)으로 정한*` (일반형: `[가-힣]*부령으로 정한`).
- **하위법령 식별**: 인덱스에서 `{모법명} 시행령`, `{모법명} 시행규칙` 정확일치.
- **축약 참조 매칭**: 하위법령 조문 본문의 `법 제N조(의M)` → 모법 조문,
  시행규칙의 `영 제N조(의M)` → 시행령 조문. (앞에 다른 한글이 붙은 "○○법 제N조"와
  구분 — 경계 정규식 `(?<![가-힣])법 제N조`.)
- **방향**:
  - source가 법률: 각 위임 조문 → `{article, article_title, phrases: [위임 문구 발췌],
    delegated_to: [{citation, article_title, snippet}]}` (delegated_to는 해당 모법
    조문을 "법 제N조"로 참조하는 하위법령 조문들)
  - source가 시행령/시행규칙: 역방향 — 각 조문의 "법/영 제N조" → 상위 조문 연결
- **정비 점검** (`sync_check` 필드): sources.json의 시행일 문자열 비교 — 모법
  시행일 > 하위법령 시행일이면 `status: "review_needed"` + 두 시행일 동봉,
  아니면 `ok`. 하위법령 없으면 `no_subordinate`.
- article 지정 시 그 조문만, 생략 시 위임 조문 전체 요약 (limit 없음 — 조문 단위
  집계라 폭주 없음; 발췌는 snippet 길이 제한).
- 오류: 대상 법령 없음 → `{"error": ...}` (find_references 관행), 입력 검증은
  서버 경계(v1.2 규약).

### 2. `startup_stage_guide(stage: Optional[str] = None) -> dict`

위치: 신규 `stages.py` + `data/stages.json` (커밋 대상 큐레이션 자산).

**stages.json 스키마**:
```json
{"stages": [{
  "id": "idea",              // 영문 id (idea/incorporation/funding/hiring/tax/ip)
  "order": 1,
  "name": "아이디어 검증·예비창업",
  "summary": "1~2문장 실무 메모",
  "key_articles": [
    {"source": "중소기업창업 지원법", "article": "제2조", "why": "창업·예비창업자의 법적 정의 — 지원사업 자격의 출발점"}
  ],
  "checklist": ["실무 체크 항목", "..."],
  "program_hints": [{"query": "예비창업", "why": "예비창업자 대상 사업화 지원"}]
}]}
```

- 6단계: 아이디어 검증·예비창업 → 법인 설립 → 자금 조달 → 첫 고용 → 세무·회계 →
  지식재산·데이터. 단계당 key_articles 3~6개, checklist 3~5개, program_hints 1~2개.
- **조회 동작**: `stage` 생략 → 6단계 개요(id·name·summary·조문 수). 지정(id 또는
  이름 부분일치, NFC) → 단계 상세: key_articles 각각을 인덱스로 검증해
  `{citation, article_title, why}` 반환(미존재 조문은 `missing: true`로 정직하게
  표시 — 침묵 누락 금지), checklist, 그리고 program_hints의 query를
  `programs.search_programs(query, limit=3)`로 실행한 결과(현재 모집 중 공고
  status·d_day 포함)를 `related_programs`로 동봉. warning(스냅샷 노후)도 전파.
- **큐레이션 품질 게이트**: pytest가 stages.json의 모든 `{source, article}`이
  실제 인덱스에 존재하는지 검증(실데이터 인덱스가 있는 로컬) — CI에는 인덱스가
  없으므로 해당 테스트는 인덱스 부재 시 skip. 픽스처 기반 단위 테스트는 별도
  테스트용 stages 픽스처로 로직 검증.
- 큐레이션 콘텐츠는 구현 단계에서 실제 인덱스를 CLI로 대조하며 작성한다.

### 3. `check_effective_date(source: str, article: Optional[str] = None) -> dict`

위치: `law_search.py`.

- `source`만: 법령 단위 — sources.json/인덱스의 시행일 → 오늘 대비
  `status: "in_force" | "upcoming"(D-N 동봉)`, 최신 부칙 블록에서
  `제1조(시행일)` 문장 발췌.
- `article` 지정: 조문 단위 — Article.effective_date(`<시행 …>` 파싱값)가 있으면
  그것으로, 없으면 법령 시행일로 판정. 추가로 그 법령의 부칙 본문에서
  해당 조문 번호(`제N조`)가 언급된 경과조치 문단(±스니펫)을 `transitional_provisions`
  배열로 발췌 (여러 부칙 블록에 걸칠 수 있음).
- `today: Optional[date]` 주입 가능 (테스트 고정, programs 관행과 동일).
- 대상 없음 → `{"error": ...}`.

## 공통 사항

- `server.py`: 도구 3개 등록(총 13개), SERVER_INSTRUCTIONS에 세 도구의 사용 시점
  안내 추가("위임·시행령 구체화 질문 → delegation_map", "창업 단계·뭘 봐야 하나 →
  startup_stage_guide", "시행 여부·경과조치 → check_effective_date"). 입력 검증은
  v1.2 규약(_require_text 등) 재사용.
- 테스트: 픽스처 확장 — 시행령 픽스처에 "법 제2조" 축약 참조·위임 문구, 법률
  픽스처에 "대통령령으로 정한다" 문구, 부칙에 경과조치 추가. 기존 105개 테스트
  기대값은 불변이어야 함 (픽스처 추가 텍스트가 기존 검색·refs 단언을 흔들지 않게
  본문 선택에 주의).
- README: 도구 13개 표 + 사용 예시 3개 추가, 로드맵 v1.3 완료 표시.
- v1.2 규약 유지: 표준 라이브러리만, NFC, invalid_input, conventional commits.
- 보류(스코프 밖): 위임 엣지 사전 계산 인덱스, 조례·행정규칙 확장, stage별
  업종 분기.

## 테스트 전략

- delegation_map: 픽스처(법률 위임 문구 ↔ 시행령 "법 제2조" 참조)로 정·역방향
  엣지, sync_check(시행일 조작 픽스처), 하위법령 없음 케이스.
- stages: 테스트 픽스처 stages로 개요/상세/부분일치/미존재 stage 오류/missing
  article 정직 표시/related_programs 동봉(programs_index 픽스처 재사용).
- check_effective_date: 조문 effective_date 유/무, upcoming D-N(today 주입),
  경과조치 발췌, 대상 없음.
- 실데이터: stages.json 실재성 검증 테스트(인덱스 없으면 skip) + CLI 스모크
  (중기창업법 delegation_map, 각 단계 1회 조회).
