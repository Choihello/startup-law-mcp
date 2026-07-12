import asyncio


def test_ten_tools_registered():
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws", "verify_citation",
                     "find_references", "search_program", "get_program",
                     "list_open_programs", "sync_programs", "data_status"}


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
