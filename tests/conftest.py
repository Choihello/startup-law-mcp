from pathlib import Path

import pytest

import law_search as ls

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def index(monkeypatch):
    arts = []
    for p in sorted(FIXTURES.glob("*.md")):
        arts.extend(ls.parse_md(p))
    monkeypatch.setattr(ls, "_INDEX_CACHE", arts)
    return arts


@pytest.fixture
def programs_index(monkeypatch):
    import programs

    monkeypatch.setattr(programs, "PROGRAMS_DIR", FIXTURES / "programs")
    monkeypatch.setattr(programs, "_CACHE", None)
    return programs
