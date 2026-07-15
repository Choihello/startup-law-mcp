import asyncio
from datetime import date

import law_search as ls
import programs
import server


def test_validators_boundaries():
    assert server._require_text("  ", "query")["status"] == "invalid_input"
    assert server._require_text(None, "query")["status"] == "invalid_input"
    assert server._require_text("창업", "query") is None
    for bad in (-1, 0, 51, True):
        assert server._check_limit(bad)["status"] == "invalid_input"
    for ok in (1, 50):
        assert server._check_limit(ok) is None
    assert server._check_enum("weird", "status", ("open", "closed"))["status"] == "invalid_input"
    assert server._check_enum(None, "status", ("open",)) is None


def test_engine_clamps_negative_limit(index):
    # clamp 전에는 scored[:-1]로 1건 결과가 0건이 됐다
    assert len(ls.search("정의", limit=-1)) == 1


def test_programs_clamps_negative_limit(programs_index):
    rows = programs.search_programs("창업", limit=-1, today=date(2026, 7, 11))["results"]
    assert len(rows) == 1  # clamp: -1 → 1


def test_registered_tool_rejects_blank_query():
    res = asyncio.run(server.mcp.call_tool("search_law", {"query": "   "}))
    assert "invalid_input" in str(res)


def test_registered_tool_rejects_bad_limit():
    res = asyncio.run(server.mcp.call_tool("search_program", {"query": "창업", "limit": -1}))
    assert "invalid_input" in str(res)


def test_registered_tool_rejects_bad_status():
    res = asyncio.run(server.mcp.call_tool("search_program", {"query": "창업", "status": "opened"}))
    assert "invalid_input" in str(res)


def test_match_programs_requires_profile():
    res = asyncio.run(server.mcp.call_tool("match_programs", {}))
    assert "invalid_input" in str(res)


def test_match_programs_rejects_pre_startup_with_years():
    res = asyncio.run(server.mcp.call_tool(
        "match_programs", {"pre_startup": True, "years": 3}))
    assert "invalid_input" in str(res)


def test_match_programs_rejects_out_of_range():
    for args in ({"age": -1}, {"age": 121}, {"years": -1}, {"years": 51},
                 {"region": "   "}, {"keyword": " "}, {"age": 30, "limit": 0}):
        res = asyncio.run(server.mcp.call_tool("match_programs", args))
        assert "invalid_input" in str(res), args
