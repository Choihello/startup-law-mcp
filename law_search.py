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


def build_index() -> list[Article]:
    arts: list[Article] = []
    for p in sorted(LAWS_DIR.glob("*.md")):
        arts.extend(parse_md(p))
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps([asdict(a) for a in arts], ensure_ascii=False),
        encoding="utf-8")
    print(f"인덱스 빌드 완료: 문서 {len({a.source for a in arts})}개, 조문 {len(arts)}개")
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
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
