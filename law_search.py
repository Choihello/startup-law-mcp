"""창업 법령 조문 인덱싱·검색 엔진 + CLI.

data/laws/*.md (Format A)를 조문 단위로 파싱해 data/index.json을 빌드하고,
검색·조회·인용검증·상호참조를 제공한다. 의존성: 표준 라이브러리만.

CLI:
  python law_search.py build
  python law_search.py search "창업 세액감면" --source 조세특례제한법
  python law_search.py get 테스트창업법 제2조
  python law_search.py verify "테스트창업법 제2조에 따라 ..."
  python law_search.py refs 테스트창업법 제2조
"""
from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LAWS_DIR = DATA / "laws"
INDEX_FILE = DATA / "index.json"


@dataclass
class Article:
    law_type: str
    source: str
    revision: str
    file: str
    chapter: str
    article: str
    article_no: int
    article_sub: int
    article_title: str
    body: str
    is_supplementary: bool = False
    effective_date: str = ""

    @property
    def citation(self) -> str:
        return f"{self.source} {self.article}"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


HEADER_RE = re.compile(r"^# (.+?) \((.+?), 시행 (.+?)\)\s*$")
CHAPTER_RE = re.compile(r"^## (?!부칙)(.+?)\s*$")
SUPPL_RE = re.compile(r"^## (부칙.*?)\s*$")
ARTICLE_HEAD_RE = re.compile(r"^### (제(\d+)조(?:의(\d+))?)(?:\((.*?)\))?\s*$")
_EFF_LINE_RE = re.compile(r"^<시행 (.+?)>\s*\n?")


def parse_md(path: Path) -> list[Article]:
    """Format A 마크다운 1개 파일 → Article 목록. 부칙은 블록 단위 1건으로 태깅."""
    text = _nfc(path.read_text(encoding="utf-8"))
    lines = text.split("\n")
    source = revision = law_type = ""
    m = HEADER_RE.match(lines[0]) if lines else None
    if m:
        source = m.group(1).strip()
        revision = "시행 " + m.group(3).strip()
    for ln in lines[1:10]:
        if ln.startswith("- 법종:"):
            law_type = ln.split(":", 1)[1].strip()

    articles: list[Article] = []
    chapter = ""
    in_suppl = False
    cur: Optional[tuple[str, int, int, str]] = None  # (article, no, sub, title)
    buf: list[str] = []
    suppl_label = ""
    suppl_buf: list[str] = []

    def flush_article() -> None:
        nonlocal cur, buf
        if cur:
            body = "\n".join(buf).strip()
            eff = ""
            em = _EFF_LINE_RE.match(body)
            if em:
                eff = em.group(1).strip()
                body = body[em.end():].lstrip("\n")
            articles.append(Article(
                law_type=law_type, source=source, revision=revision,
                file=path.name, chapter=chapter, article=cur[0],
                article_no=cur[1], article_sub=cur[2], article_title=cur[3],
                body=body, is_supplementary=False, effective_date=eff))
        cur, buf = None, []

    def flush_suppl() -> None:
        nonlocal suppl_label, suppl_buf
        if suppl_label:
            body = "\n".join(suppl_buf).strip()
            if body:
                articles.append(Article(
                    law_type=law_type, source=source, revision=revision,
                    file=path.name, chapter="부칙", article=suppl_label,
                    article_no=0, article_sub=0, article_title="부칙",
                    body=body, is_supplementary=True))
        suppl_label, suppl_buf = "", []

    for ln in lines[1:]:
        sm = SUPPL_RE.match(ln)
        if sm:
            flush_article()
            flush_suppl()
            in_suppl = True
            suppl_label = sm.group(1).strip()
            continue
        if in_suppl:
            suppl_buf.append(ln)
            continue
        cm = CHAPTER_RE.match(ln)
        if cm:
            flush_article()
            chapter = cm.group(1).strip()
            continue
        am = ARTICLE_HEAD_RE.match(ln)
        if am:
            flush_article()
            cur = (am.group(1), int(am.group(2)), int(am.group(3) or 0),
                   (am.group(4) or "").strip())
            continue
        if cur:
            buf.append(ln)
    flush_article()
    flush_suppl()
    return articles


def _manifest_files() -> Optional[set[str]]:
    """sources.json 등재 파일명 집합. 매니페스트가 없으면 None(전체 인덱싱 폴백)."""
    src = DATA / "sources.json"
    if not src.exists():
        return None
    try:
        manifest = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    files = {s.get("file") for s in manifest.get("sources", []) if s.get("file")}
    return files or None


def build_index() -> list[Article]:
    global _INDEX_CACHE
    allowed = _manifest_files()
    arts: list[Article] = []
    skipped: list[str] = []
    for p in sorted(LAWS_DIR.glob("*.md")):
        if allowed is not None and p.name not in allowed:
            skipped.append(p.name)
            continue
        arts.extend(parse_md(p))
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps([asdict(a) for a in arts], ensure_ascii=False),
        encoding="utf-8")
    _INDEX_CACHE = arts  # 재빌드 즉시 캐시 갱신 — stale 캐시 방지
    msg = f"인덱스 빌드 완료: 문서 {len({a.source for a in arts})}개, 조문 {len(arts)}개"
    if skipped:
        msg += f" (매니페스트 외 {len(skipped)}개 제외)"
    print(msg)
    return arts


_INDEX_CACHE: Optional[list[Article]] = None


def load_index(use_cache: bool = True) -> list[Article]:
    global _INDEX_CACHE
    if use_cache and _INDEX_CACHE is not None:
        return _INDEX_CACHE
    if not INDEX_FILE.exists():
        raise RuntimeError(
            "인덱스가 없습니다. 먼저 `python law_search.py build`를 실행하세요.")
    names = {f.name for f in fields(Article)}
    data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    _INDEX_CACHE = [Article(**{k: v for k, v in d.items() if k in names}) for d in data]
    return _INDEX_CACHE


STOPWORDS = {
    "다음", "중", "것", "것은", "것을", "어느", "어떤", "해당", "관한", "관하여",
    "대한", "대하여", "위한", "위하여", "그리고", "그러나", "또는", "다만", "각",
    "사항", "내용", "경우", "방법", "이상", "이하", "초과", "미만",
    "한다", "있다", "없다", "수", "또", "이", "무엇", "어떻게",
}

JOSA_RE = re.compile(
    r"(으로부터|에서의|으로써|이란|란|으로|로|의|를|을|은|는|이|가|과|와|에게|에서|에|도|만)$")


def tokenize(query: str) -> list[str]:
    query = _nfc(query)
    out: list[str] = []
    for tok in re.split(r"[\s,·、]+", query.strip()):
        tok = tok.strip("().,!?\"'·")
        if not tok:
            continue
        stripped = JOSA_RE.sub("", tok)
        candidate = stripped if len(stripped) >= 2 else tok
        if candidate in STOPWORDS or len(candidate) < 2:
            continue
        out.append(candidate)
    seen: set[str] = set()
    return [t for t in out if not (t in seen or seen.add(t))]


_SOURCE_CONNECTOR_RE = re.compile(r"에관한|관한|의|및|와|과|등에서의|등")


def _normalize_source(s: str) -> str:
    s = re.sub(r"[\s·․‧・]+", "", _nfc(s))
    return _SOURCE_CONNECTOR_RE.sub("", s)


def source_match(query: str, source_label: str) -> bool:
    """법령명 부분일치 (3단계): 직접 substring → 공백 토큰 전부 등장 → 정규화 substring."""
    if not query:
        return True
    q = _nfc(query).strip()
    s = _nfc(source_label)
    if not q:
        return True
    if q in s:
        return True
    tokens = [t for t in re.split(r"\s+", q) if len(t) >= 2]
    if tokens and all(t in s for t in tokens):
        return True
    nq = _normalize_source(q)
    if nq and nq in _normalize_source(s):
        return True
    return False


def compute_idf(tokens: list[str], articles: list[Article]) -> dict[str, float]:
    n = len(articles)
    idf: dict[str, float] = {}
    for t in tokens:
        df = sum(1 for a in articles
                 if t in a.body or t in a.article_title or t in a.chapter)
        idf[t] = math.log((n + 1) / (df + 1)) + 1.0
    return idf


def _bigrams(s: str) -> list[str]:
    return [s[i:i + 2] for i in range(len(s) - 1)]


def score_article(a: Article, tokens: list[str],
                  idf: Optional[dict[str, float]] = None,
                  fuzzy: bool = False) -> tuple[float, int]:
    score = 0.0
    first_pos = -1
    body = a.body
    for tok in tokens:
        w = idf[tok] if idf else 1.0
        if tok in a.article_title:
            score += 5.0 * w
        if tok in a.chapter:
            score += 2.0 * w
        cnt = body.count(tok)
        if cnt:
            score += float(cnt) * w
            pos = body.find(tok)
            if first_pos < 0 or pos < first_pos:
                first_pos = pos
        elif fuzzy and len(tok) >= 3:
            bgs = _bigrams(tok)
            hit_kinds = sum(1 for b in bgs if b in body)
            if hit_kinds >= len(bgs) * 0.5:
                bg_hits = sum(body.count(b) for b in bgs)
                score += (bg_hits / len(bgs)) * 0.3 * w
                if first_pos < 0:
                    for b in bgs:
                        p = body.find(b)
                        if p >= 0:
                            first_pos = p
                            break
    return score, first_pos


_META_NOISE_RE = re.compile(
    r"<(?:개정|신설|삭제|단서개정|제목개정|전부개정|시행)[^>]*?>"
    r"|\[(?:개정|신설|삭제|제목개정|단서개정|전부개정|전문개정)[^\]]*?\]")


def _strip_meta(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _META_NOISE_RE.sub("", text)).strip()


def make_snippet(body: str, pos: int, span: int = 80) -> str:
    if not body:
        return ""
    if pos < 0:
        s = _strip_meta(body[: span * 2].replace("\n", " "))
        return s + ("…" if len(body) > span * 2 else "")
    start = max(0, pos - span)
    end = min(len(body), pos + span)
    s = _strip_meta(body[start:end].replace("\n", " "))
    if start > 0:
        s = "…" + s
    if end < len(body):
        s = s + "…"
    return s


def search(query: str, law_type: Optional[str] = None,
           source: Optional[str] = None, limit: int = 10,
           fuzzy: bool = False) -> list[dict]:
    articles = load_index()
    tokens = tokenize(query)
    if not tokens:
        return []
    idf = compute_idf(tokens, articles)
    scored: list[tuple[float, int, Article]] = []
    for a in articles:
        if law_type and a.law_type != law_type:
            continue
        if source and not source_match(source, a.source):
            continue
        sc, pos = score_article(a, tokens, idf, fuzzy=fuzzy)
        if a.is_supplementary:
            sc *= 0.2  # 부칙 블록은 길어 원시 TF가 과대 — 본칙 우선 노출
        if sc <= 0:
            continue
        scored.append((sc, pos, a))
    scored.sort(key=lambda r: r[0], reverse=True)
    return [{
        "law_type": a.law_type,
        "source": a.source,
        "revision": a.revision,
        "chapter": a.chapter,
        "article": a.article,
        "article_title": a.article_title,
        "citation": a.citation,
        "snippet": make_snippet(a.body, pos),
        "score": round(sc, 2),
    } for sc, pos, a in scored[:limit]]


ARTICLE_TOKEN_RE = re.compile(r"^\s*(?:제)?(\d+)조?(?:의(\d+))?\s*$")


def _parse_article_token(token: str) -> Optional[tuple[int, int]]:
    t = _nfc(str(token)).strip()
    m = ARTICLE_TOKEN_RE.match(t)
    if m:
        return int(m.group(1)), int(m.group(2) or 0)
    m2 = re.search(r"제(\d+)조(?:의(\d+))?", t)
    if m2:
        return int(m2.group(1)), int(m2.group(2) or 0)
    return None


def _source_selector(query: Optional[str], articles: list[Article]):
    """법령명 매칭 술어. 정확일치(NFC)가 있으면 그 법령으로 한정 —
    '테스트창업법'이 '테스트창업법 시행령'까지 번지는 모호성 차단."""
    if not query:
        return lambda s: True
    q = _nfc(query).strip()
    if any(a.source == q for a in articles):
        return lambda s: s == q
    return lambda s: source_match(query, s)


def get_article(source: str, article: str) -> list[dict]:
    """법령명 매칭(정확일치 우선) + 조문번호 정확매칭. 본칙 우선."""
    parsed = _parse_article_token(article)
    if parsed is None:
        return []
    no, sub = parsed
    arts = load_index()
    src_ok = _source_selector(source, arts)
    matches = [a for a in arts
               if src_ok(a.source) and a.article_no == no and a.article_sub == sub]
    main = [a for a in matches if not a.is_supplementary]
    chosen = main if main else matches
    return [{
        "law_type": a.law_type,
        "source": a.source,
        "revision": a.revision,
        "chapter": a.chapter,
        "article": a.article,
        "article_title": a.article_title,
        "citation": a.citation,
        "body": a.body,
        "effective_date": a.effective_date,
        "is_supplementary": a.is_supplementary,
    } for a in chosen]


def list_laws(law_type: Optional[str] = None) -> list[dict]:
    by_src: dict[str, dict] = {}
    for a in load_index():
        if law_type and a.law_type != law_type:
            continue
        if a.source not in by_src:
            by_src[a.source] = {
                "source": a.source,
                "law_type": a.law_type,
                "revision": a.revision,
                "article_count": 0,
            }
        by_src[a.source]["article_count"] += 1
    return sorted(by_src.values(), key=lambda x: (x["law_type"], x["source"]))


CITATION_RE = re.compile(
    r"제(\d+)조(?:의(\d+))?(?:\s*제\d+항)?(?:\s*제\d+호)?(?:\s*\(([^)]{2,40})\))?")
_DEF_PAREN_RE = re.compile('이하|약칭|[\'"‘’“”]|(?:이)?라\\s*(?:한다|칭한다)')


def _title_key(s: str) -> str:
    return re.sub(r"[\s·․.,'\"()\[\]「」]", "", _nfc(s))


def _title_matches(cited: str, actual: str) -> bool:
    """인용 제목이 실제 제목의 부분(축약)이면 일치, 수식어를 덧붙였으면 환각.
    그 외 음절 bigram Jaccard ≥ 0.4면 이표기로 간주."""
    c, a = _title_key(cited), _title_key(actual)
    if not c or not a:
        return True
    if c == a or c in a:
        return True
    cb, ab = set(_bigrams(c)), set(_bigrams(a))
    if not cb or not ab:
        return True
    return len(cb & ab) / len(cb | ab) >= 0.4


def _article_range_for(source_nfc: str, articles: list[Article]) -> str:
    nos = sorted({(a.article_no, a.article_sub) for a in articles
                  if source_nfc in a.source and not a.is_supplementary})
    if not nos:
        return "(해당 법령 없음)"
    def lab(t):
        return f"제{t[0]}조" + (f"의{t[1]}" if t[1] else "")
    return f"{lab(nos[0])} ~ {lab(nos[-1])}, 총 {len(nos)}개"


def verify_citation(text: str) -> list[dict]:
    """텍스트 내 모든 '{법령명} 제N조[의M][(제목)]' 인용을 인덱스로 교차검증."""
    text_nfc = _nfc(text)
    articles = load_index()
    known_sources = sorted({a.source for a in articles}, key=len, reverse=True)

    def nearest_source(prefix: str) -> Optional[str]:
        best, best_pos = None, -1
        for src in known_sources:
            pos = prefix.rfind(src)
            if pos > best_pos or (pos == best_pos and best and len(src) > len(best)):
                best_pos, best = pos, src
        return best if best_pos >= 0 else None

    results = []
    for m in CITATION_RE.finditer(text_nfc):
        prefix = text_nfc[max(0, m.start() - 80): m.start()]
        matched_src = nearest_source(prefix)
        art = f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "")
        full_cite = text_nfc[m.start(): m.end()]
        if not matched_src:
            results.append({
                "citation": full_cite,
                "status": "unknown_source",
                "message": "직전 텍스트에서 인덱싱된 법령명을 찾지 못함",
            })
            continue
        no, sub = int(m.group(1)), int(m.group(2) or 0)
        cand = [a for a in articles
                if a.source == matched_src and a.article_no == no
                and a.article_sub == sub and not a.is_supplementary]
        hit = cand[0] if cand else None
        if hit:
            cited_title = (m.group(3) or "").strip()
            check_title = bool(cited_title) and not _DEF_PAREN_RE.search(cited_title)
            if check_title and not _title_matches(cited_title, hit.article_title):
                results.append({
                    "citation": f"{matched_src} {art}",
                    "raw_match": full_cite,
                    "status": "content_mismatch",
                    "cited_title": cited_title,
                    "actual_title": hit.article_title,
                    "message": f"{matched_src} {art}의 실제 제목은 '{hit.article_title}' — "
                               f"인용의 '{cited_title}'와 불일치 (내용 환각 가능)",
                })
            else:
                results.append({
                    "citation": f"{matched_src} {art}",
                    "raw_match": full_cite,
                    "status": "ok",
                    "article_title": hit.article_title,
                    "title_verified": check_title,
                    "body_excerpt": _strip_meta(hit.body[:250].replace("\n", " "))[:150],
                })
        else:
            results.append({
                "citation": f"{matched_src} {art}",
                "raw_match": full_cite,
                "status": "not_found",
                "message": f"{matched_src}에 {art} 없음 "
                           f"(실재: {_article_range_for(matched_src, articles)})",
            })
    return results


_SAME_LAW_CITE_RE = re.compile(r"(?<![가-힣A-Za-z0-9_])제(\d+)조(?:의(\d+))?")
_EXTERNAL_CITE_RE = re.compile(
    r"(?:「([^」\n]{2,40}?)」"
    r"|((?:[가-힣]+\s?){1,6}?(?:법률|시행령|시행규칙|법|규칙|령)))"
    r"\s*제(\d+)조(?:의(\d+))?")


def _around(body: str, pos: int, span: int = 60) -> str:
    start = max(0, pos - span)
    end = min(len(body), pos + span)
    s = _strip_meta(body[start:end].replace("\n", " "))
    return ("…" if start > 0 else "") + s + ("…" if end < len(body) else "")


def find_references(source: str, article: str, limit: int = 20,
                    include_mermaid: bool = False) -> dict:
    """대상 조문의 정방향(outgoing)·역방향(incoming) 인용 관계.

    scope: same_law(같은 법령 안) / cross_law(인덱스 내 다른 법령) /
    external(인덱스에 없는 법령).
    """
    parsed = _parse_article_token(article)
    if parsed is None:
        return {"error": f"조문 토큰 해석 불가: {article!r}"}
    no, sub = parsed
    articles = load_index()
    src_ok = _source_selector(source, articles)
    targets = [a for a in articles
               if src_ok(a.source) and a.article_no == no and a.article_sub == sub]
    if not targets:
        return {"error": f"대상 조문 없음: {source} 제{no}조" + (f"의{sub}" if sub else "")}
    targets.sort(key=lambda a: a.is_supplementary)  # 본칙 우선
    target = targets[0]
    known_sources = sorted({a.source for a in articles}, key=len, reverse=True)

    # ===== OUTGOING =====
    outgoing: list[dict] = []
    seen: set[tuple] = set()
    consumed: list[tuple[int, int]] = []
    for m in _EXTERNAL_CITE_RE.finditer(target.body):
        cited_name = re.sub(r"\s+", "", (m.group(1) or m.group(2) or ""))
        c_no, c_sub = int(m.group(3)), int(m.group(4) or 0)
        key = (cited_name, c_no, c_sub)
        if key in seen:
            continue
        seen.add(key)
        consumed.append((m.start(), m.end()))
        # 정확일치(공백 무시) 우선 — "테스트창업법"이 "테스트창업법 시행령"으로
        # 오귀속되는 접두 충돌 방지. 정확일치가 없을 때만 substring 폴백.
        matched = next((s for s in known_sources
                        if s.replace(" ", "") == cited_name), None)
        if matched is None:
            matched = next((s for s in known_sources
                            if cited_name in s.replace(" ", "")
                            or s.replace(" ", "") in cited_name), None)
        if matched:
            cited = next((a for a in articles
                          if a.source == matched and a.article_no == c_no
                          and a.article_sub == c_sub and not a.is_supplementary), None)
            if cited:
                scope = "same_law" if matched == target.source else "cross_law"
                outgoing.append({
                    "scope": scope,
                    "citation": cited.citation,
                    "article_title": cited.article_title,
                    "snippet": _strip_meta(cited.body[:200].replace("\n", " "))[:120],
                })
                continue
        outgoing.append({
            "scope": "external",
            "citation": f"{cited_name} 제{c_no}조" + (f"의{c_sub}" if c_sub else ""),
            "note": "인덱스에 없는 외부 법령 또는 조문 매칭 실패",
        })
    for m in _SAME_LAW_CITE_RE.finditer(target.body):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        c_no, c_sub = int(m.group(1)), int(m.group(2) or 0)
        if (c_no, c_sub) == (no, sub):
            continue
        key = (target.source, c_no, c_sub)
        if key in seen:
            continue
        seen.add(key)
        cited = next((a for a in articles
                      if a.source == target.source and a.article_no == c_no
                      and a.article_sub == c_sub and not a.is_supplementary), None)
        if cited:
            outgoing.append({
                "scope": "same_law",
                "citation": cited.citation,
                "article_title": cited.article_title,
                "snippet": _strip_meta(cited.body[:200].replace("\n", " "))[:120],
            })

    # ===== INCOMING =====
    incoming: list[dict] = []
    for a in articles:
        if a is target or a.is_supplementary:
            continue
        if a.source == target.source:
            for m in _SAME_LAW_CITE_RE.finditer(a.body):
                if int(m.group(1)) == no and int(m.group(2) or 0) == sub:
                    incoming.append({
                        "scope": "same_law",
                        "citation": a.citation,
                        "article_title": a.article_title,
                        "snippet": _around(a.body, m.start()),
                    })
                    break
        else:
            if target.source not in a.body:
                continue
            pos = 0
            while True:
                idx = a.body.find(target.source, pos)
                if idx < 0:
                    break
                after = a.body[idx + len(target.source): idx + len(target.source) + 60]
                # 「법령명」 제N조 형태 — 닫는 낫표·괄호를 건너뛰고 조번호 매칭
                m = re.match(r"\s*[」』\)]?\s*제(\d+)조(?:의(\d+))?", after)
                if m and int(m.group(1)) == no and int(m.group(2) or 0) == sub:
                    incoming.append({
                        "scope": "cross_law",
                        "citation": a.citation,
                        "article_title": a.article_title,
                        "snippet": _around(a.body, idx),
                    })
                    break
                pos = idx + len(target.source)

    result = {
        "target": {
            "source": target.source,
            "article": target.article,
            "article_title": target.article_title,
            "citation": target.citation,
        },
        "outgoing": outgoing[:limit],
        "incoming": incoming[:limit],
        "counts": {"outgoing": len(outgoing), "incoming": len(incoming)},
    }
    if include_mermaid:
        result["mermaid"] = _mermaid_graph(result)
    return result


def _mermaid_graph(result: dict) -> str:
    """incoming → target → outgoing flowchart."""
    lines = ["flowchart LR"]
    tid = "T"
    t = result["target"]
    lines.append(f'    {tid}["{t["citation"]}({t["article_title"]})"]')
    for i, ref in enumerate(result["incoming"]):
        lines.append(f'    I{i}["{ref["citation"]}"] --> {tid}')
    for i, ref in enumerate(result["outgoing"]):
        lines.append(f'    {tid} --> O{i}["{ref["citation"]}"]')
    return "\n".join(lines)


def cmd_build(_args: argparse.Namespace) -> None:
    build_index()


def cmd_search(args: argparse.Namespace) -> None:
    for r in search(args.query, law_type=args.law_type, source=args.source,
                    limit=args.limit, fuzzy=args.fuzzy):
        print(f"[{r['score']:>6}] {r['citation']}({r['article_title']})")
        print(f"        {r['snippet']}")


def cmd_get(args: argparse.Namespace) -> None:
    for h in get_article(args.source, args.article):
        print(f"== {h['citation']}({h['article_title']}) [{h['revision']}]")
        print(h["body"])


def cmd_verify(args: argparse.Namespace) -> None:
    for r in verify_citation(args.text):
        print(f"[{r['status']}] {r['citation']}" +
              (f" — {r.get('message', '')}" if r.get("message") else ""))


def cmd_refs(args: argparse.Namespace) -> None:
    r = find_references(args.source, args.article)
    print(json.dumps(r, ensure_ascii=False, indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("build", help="data/laws/*.md → index.json")
    pb.set_defaults(func=cmd_build)
    psr = sub.add_parser("search", help="조문 검색")
    psr.add_argument("query")
    psr.add_argument("--law-type", dest="law_type", default=None)
    psr.add_argument("--source", default=None)
    psr.add_argument("--limit", type=int, default=10)
    psr.add_argument("--fuzzy", action="store_true")
    psr.set_defaults(func=cmd_search)
    pg = sub.add_parser("get", help="조문 본문 조회")
    pg.add_argument("source")
    pg.add_argument("article")
    pg.set_defaults(func=cmd_get)
    pv = sub.add_parser("verify", help="조문 인용 실재성 검증")
    pv.add_argument("text")
    pv.set_defaults(func=cmd_verify)
    pr = sub.add_parser("refs", help="조문 상호참조")
    pr.add_argument("source")
    pr.add_argument("article")
    pr.set_defaults(func=cmd_refs)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
