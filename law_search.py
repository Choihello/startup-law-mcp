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


def cmd_build(_args: argparse.Namespace) -> None:
    build_index()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("build", help="data/laws/*.md → index.json")
    pb.set_defaults(func=cmd_build)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
