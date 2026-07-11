import asyncio


def test_nine_tools_registered():
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws", "verify_citation",
                     "find_references", "search_program", "get_program",
                     "list_open_programs", "sync_programs"}


def test_instructions_mention_both_axes():
    import server

    assert "창업" in server.SERVER_INSTRUCTIONS
    assert "search_law" in server.SERVER_INSTRUCTIONS
    assert "search_program" in server.SERVER_INSTRUCTIONS
