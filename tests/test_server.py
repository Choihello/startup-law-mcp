import asyncio


def test_five_tools_registered():
    import server
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"search_law", "get_article", "list_laws",
                     "verify_citation", "find_references"}


def test_instructions_mention_domain():
    import server
    assert "창업" in server.SERVER_INSTRUCTIONS
    assert "search_law" in server.SERVER_INSTRUCTIONS
