# startup-law-mcp v1.4 주간 자동 동기화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매주 법령+지원사업 자동 동기화 → 변경 시 자동 PR (사람 검토·머지) + v1.3 백로그(경과조치 재현율) 수용.

**Architecture:** GitHub Actions 워크플로 1개(schedule + dispatch)가 기존 sync CLI들을 그대로 실행 — 코드 재사용, 신규 로직은 워크플로 조립뿐. v1.2 sync 방어와 stages 실재성 게이트가 PR 전 안전판으로 작동.

**Tech Stack:** GitHub Actions (actions/checkout@v4, setup-python@v5, peter-evans/create-pull-request@v6). Python 코드 변경은 정규식 1곳.

**스펙:** [docs/superpowers/specs/2026-07-13-weekly-sync-v1.4-design.md](../specs/2026-07-13-weekly-sync-v1.4-design.md)

## Global Constraints

- 워크플로는 main에 직접 push 금지 — `auto/weekly-sync` 브랜치 + PR만.
- run 스텝에서 파이프(`| tee`) 사용 시 **`set -o pipefail` 필수** (sync 실패가 tee에 가려지면 안 됨 — GH Actions bash 기본은 pipefail 아님).
- 시크릿은 `${{ secrets.LAW_OC }}`, `${{ secrets.DATA_GO_KR_KEY }}`로만 — 값 리터럴 금지.
- label_re 회복: `re.escape(label) + r"(?:제\d+항)*(?!(?:의|제)\d)"` — 제N조제M항 허용, 제N조의M·제N조제M호 차단 유지. 기존 정밀도 테스트(test_transitional_precision) 불변 통과.
- PYTHONUTF8=1 (한글 로그·경로). conventional commits. `python -m pytest`.

---

### Task 1: 경과조치 재현율 회복 (제N조제M항 허용)

**Files:**
- Modify: `law_search.py` (check_effective_date 안 label_re 1줄)
- Test: `tests/test_effective_date.py`

**Interfaces:**
- Consumes: 기존 `check_effective_date` (v1.3 정밀도 fix 상태 — 제목 화이트리스트 상태기계)
- Produces: 동작 확장만 — 반환 스키마 불변.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_effective_date.py` 끝에:

```python
def test_transitional_hang_suffix_is_valid_mention(monkeypatch):
    # '제23조제1항'은 제23조의 유효한 언급 — 재현율 회복 (v1.3 최종리뷰 백로그)
    suppl_body = (
        "제1조(시행일) 이 법은 2026년 1월 1일부터 시행한다.\n"
        "제2조(경과조치) 이 법 시행 전 종전의 제23조제1항에 따른 처분은 유효하다.")
    arts = [
        ls.Article(law_type="법률", source="회복법", revision="시행 2026.01.01", file="f",
                   chapter="", article="제23조", article_no=23, article_sub=0,
                   article_title="해고 제한", body="본문"),
        ls.Article(law_type="법률", source="회복법", revision="시행 2026.01.01", file="f",
                   chapter="부칙", article="부칙 <제1호, 2025.12.01>", article_no=0,
                   article_sub=0, article_title="부칙", body=suppl_body,
                   is_supplementary=True),
    ]
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    r = ls.check_effective_date("회복법", article="제23조", today=date(2026, 7, 12))
    assert len(r["transitional_provisions"]) == 1
    assert "제23조제1항" in r["transitional_provisions"][0]["snippet"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_effective_date.py::test_transitional_hang_suffix_is_valid_mention -v`
Expected: FAIL — transitional_provisions가 0건 (lookahead가 제1항을 차단)

- [ ] **Step 3: 구현** — `law_search.py`의 `check_effective_date` 안:

```python
    label_re = re.compile(re.escape(label) + r"(?!(?:의|제)\d)")
```
를 다음으로 교체:
```python
    # '제N조제M항'은 그 조문의 유효한 언급(항 접미 허용).
    # '제N조의M'(다른 조문)·'제N조제M호'(타법개정 보일러플레이트)는 계속 차단.
    label_re = re.compile(re.escape(label) + r"(?:제\d+항)*(?!(?:의|제)\d)")
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_effective_date.py -v` → 8 passed (기존 정밀도 테스트 포함 전부).
전체: `python -m pytest tests/ -q` → 126 passed.
실데이터: `python -X utf8 -c "import law_search as ls; r = ls.check_effective_date('근로기준법', article='제23조'); print(len(r['transitional_provisions']), r['transitional_provisions'][:1])"` — v1.3에서 0건이던 것이 이제 ≥1건 (경과조치의 '제23조제1항' 회복) — 출력을 리포트에 수록.

- [ ] **Step 5: Commit**

```bash
git add law_search.py tests/test_effective_date.py
git commit -m "fix: 경과조치 재현율 회복 — 제N조제M항 접미를 유효 언급으로"
```

---

### Task 2: 주간 동기화 워크플로 + README

**Files:**
- Create: `.github/workflows/weekly-sync.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `law_sync.py sync`·`law_search.py build`·`program_sync.py sync` CLI (환경변수 LAW_OC/DATA_GO_KR_KEY), 전체 pytest.
- Produces: 주간 PR 파이프라인. E2E는 병합·push 후 컨트롤러가 수행(Task 3) — 이 태스크에서는 YAML 유효성과 문서만.

- [ ] **Step 1: 워크플로 작성** — `.github/workflows/weekly-sync.yml`:

```yaml
name: weekly-sync
on:
  schedule:
    - cron: "0 21 * * 0"   # 일 21:00 UTC = 월 06:00 KST
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements-dev.txt

      - name: 법령 동기화 + 인덱스 빌드
        env:
          LAW_OC: ${{ secrets.LAW_OC }}
          PYTHONUTF8: "1"
        run: |
          set -o pipefail
          python law_sync.py sync 2>&1 | tee sync_law.log
          python law_search.py build

      - name: 지원사업 동기화
        env:
          DATA_GO_KR_KEY: ${{ secrets.DATA_GO_KR_KEY }}
          PYTHONUTF8: "1"
        run: |
          set -o pipefail
          python program_sync.py sync 2>&1 | tee sync_programs.log

      - name: 전체 테스트 (실재성 게이트 포함)
        env:
          PYTHONUTF8: "1"
        run: python -m pytest tests/ -q

      - name: PR 본문 조립
        id: summary
        run: |
          {
            echo "body<<SYNCEOF"
            echo "## 주간 자동 동기화 결과"
            echo ""
            echo "### 법령"
            echo '```'
            tail -n 5 sync_law.log
            echo '```'
            echo "### 지원사업"
            echo '```'
            tail -n 3 sync_programs.log
            echo '```'
            echo ""
            echo "동기화 안전 검증(급감·스키마)과 전체 테스트(큐레이션 실재성 포함)를 통과한 상태입니다. 검토 후 머지해 주세요."
            echo "SYNCEOF"
          } >> "$GITHUB_OUTPUT"

      - name: PR 생성 (변경 시에만)
        uses: peter-evans/create-pull-request@v6
        with:
          branch: auto/weekly-sync
          delete-branch: true
          title: "data: 주간 자동 동기화"
          commit-message: "data: 주간 자동 동기화 (법령 + 지원사업)"
          body: ${{ steps.summary.outputs.body }}
          add-paths: |
            data/laws/**
            data/sources.json
            data/programs/**
```

- [ ] **Step 2: YAML 유효성 확인**

Run: `python -c "import yaml, io; yaml.safe_load(open('.github/workflows/weekly-sync.yml', encoding='utf-8')); print('valid')"` — PyYAML이 없으면 `pip install pyyaml` 대신 `python -c "import json"`류 대체 불가하므로, 없을 경우 `gh workflow list`는 push 전이라 불가 — **actionlint가 없으니 최소한 들여쓰기·따옴표를 육안 재검토**하고, 리포트에 "정적 검증 방법: PyYAML parse"를 남겨라 (PyYAML은 GH Actions 이미지에 기본 포함이지만 로컬엔 없을 수 있음 — `pip show pyyaml`로 확인 후 없으면 설치).

- [ ] **Step 3: README 갱신**

- "현행성 유지" 섹션에 **자동 동기화 (v1.4)** 문단 추가: 매주 월요일 아침(KST) 법령+지원사업을 자동 동기화해 변경이 있으면 `auto/weekly-sync` 브랜치로 PR이 생성되고, 사람이 검토·머지한다. 급감·스키마 이상이면 PR 없이 워크플로가 실패한다(기존 데이터 보존). 포크·자가 호스팅 시 필요한 설정: Actions Secrets에 `LAW_OC`·`DATA_GO_KR_KEY` 등록 + Settings → Actions → General에서 Workflow permissions "Read and write" 및 "Allow GitHub Actions to create and approve pull requests" 활성화. 수동 실행은 Actions 탭 → weekly-sync → Run workflow.
- 로드맵: v1.4 완료(현재) 표시 → v2.0 원격 배포.

- [ ] **Step 4: 확인 + Commit**

Run: `python -m pytest tests/ -q` → 126 passed (워크플로·문서만 추가라 불변)

```bash
git add .github/workflows/weekly-sync.yml README.md
git commit -m "ci: 주간 자동 동기화 워크플로 (auto PR) + README 안내"
```

---

### Task 3: (컨트롤러 수행, 병합·push 후) 저장소 설정 + E2E

**전제:** Task 1·2가 main에 병합·push된 후에만 가능 (workflow_dispatch는 기본 브랜치 기준).

- [ ] **Step 1: 시크릿 등록** — `gh secret set LAW_OC`·`gh secret set DATA_GO_KR_KEY` (값은 세션 보유분)
- [ ] **Step 2: 워크플로 권한** — `gh api -X PUT repos/Choihello/startup-law-mcp/actions/permissions/workflow -f default_workflow_permissions=write -F can_approve_pull_request_reviews=true`
- [ ] **Step 3: 수동 트리거** — `gh workflow run weekly-sync` → 완료 대기 → 결과 확인:
  - 성공 + 변경 있음 → `auto/weekly-sync` PR 생성 확인, PR 본문에 동기화 요약 존재 → **PR은 사용자 확인 후 머지** (자동 머지 금지)
  - 성공 + 변경 없음 → PR 미생성 (정상)
  - 실패 → 로그로 원인 파악 (시크릿·권한·방어 로직 중 무엇인지) 후 보고
- [ ] **Step 4: 사용자에게 결과 보고** (PR 링크 또는 무변경 확인)
