import law_search as ls


def test_refs_outgoing_same_and_external(index):
    r = ls.find_references("테스트창업법", "제2조의2")
    assert r["target"]["citation"] == "테스트창업법 제2조의2"
    scopes = {(o["scope"], o["citation"]) for o in r["outgoing"]}
    assert ("same_law", "테스트창업법 제2조") in scopes
    assert ("external", "조세특례제한법 제6조") in scopes


def test_refs_incoming_cross_law(index):
    r = ls.find_references("테스트창업법", "제2조")
    incoming = {(i["scope"], i["citation"]) for i in r["incoming"]}
    assert ("cross_law", "테스트창업법 시행령 제3조") in incoming
    assert ("same_law", "테스트창업법 제2조의2") in incoming


def test_refs_invalid_target(index):
    r = ls.find_references("테스트창업법", "제99조")
    assert "error" in r


def test_refs_mermaid(index):
    r = ls.find_references("테스트창업법", "제2조", include_mermaid=True)
    assert r["mermaid"].startswith("flowchart LR")
    assert "테스트창업법 제2조" in r["mermaid"]
