import asyncio


def test_registered_tool_names():
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws", "verify_citation",
                     "find_references", "search_program", "get_program",
                     "list_open_programs", "match_programs", "sync_programs", "data_status",
                     "delegation_map", "startup_stage_guide", "check_effective_date"}


def test_instructions_mention_both_axes():
    import server

    assert "창업" in server.SERVER_INSTRUCTIONS
    assert "search_law" in server.SERVER_INSTRUCTIONS
    assert "search_program" in server.SERVER_INSTRUCTIONS


def test_data_status_tool_shape():
    # 등록 표면을 통해 실제 호출 — 환경(인덱스 유무)에 관대한 구조 단언
    import server

    res = asyncio.run(server.mcp.call_tool("data_status", {}))
    s = str(res)
    assert "programs" in s
    assert "announcement_count" in s and "intro_count" in s and "warnings" in s
    assert ("article_count" in s) or ("인덱스가 없습니다" in s)  # 인덱스 있으면 건수, 없으면 error 분기


def test_instructions_mention_v13_tools():
    import server

    for t in ("delegation_map", "startup_stage_guide", "check_effective_date"):
        assert t in server.SERVER_INSTRUCTIONS


def test_remote_surface_excludes_admin():
    from mcp.server.fastmcp import FastMCP

    import server

    remote = FastMCP("startup-law-remote-test",
                     instructions=server.SERVER_INSTRUCTIONS)
    server.register_tools(remote, include_admin=False)
    remote_names = {t.name for t in asyncio.run(remote.list_tools())}
    assert "sync_programs" not in remote_names
    assert len(remote_names) == 13
    local_names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert local_names - remote_names == {"sync_programs"}


def test_server_http_module_surface():
    import server_http

    names = {t.name for t in asyncio.run(server_http.mcp.list_tools())}
    assert "sync_programs" not in names
    assert len(names) == 13
