import json
from pathlib import Path

import pytest

import law_sync

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """DATA/LAWS_DIR을 tmp로 돌리고 laws.json·가짜 API를 세팅."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "laws.json").write_text(json.dumps({
        "laws": [
            {"name": "테스트창업법", "group": "테스트"},
            {"name": "존재하지않는법", "group": "테스트"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(law_sync, "DATA", data)
    monkeypatch.setattr(law_sync, "LAWS_DIR", data / "laws")

    sample = json.loads((FIXTURES / "sample_law.json").read_text(encoding="utf-8"))

    def fake_list(oc, query):
        if query == "테스트창업법":
            return [
                {"법령명한글": "테스트창업법", "법령일련번호": "111"},
                {"법령명한글": "테스트창업법 시행령", "법령일련번호": "222"},
                {"법령명한글": "전혀다른법", "법령일련번호": "999"},
            ]
        return []

    def fake_fetch(oc, mst):
        if mst == "111":
            return sample
        if mst == "222":
            dele = json.loads(json.dumps(sample))  # deep copy
            dele["법령"]["기본정보"]["법령명_한글"] = "테스트창업법 시행령"
            dele["법령"]["기본정보"]["법종구분"] = {"content": "대통령령"}
            return dele
        raise RuntimeError("unknown mst")

    monkeypatch.setattr(law_sync, "fetch_law_list", fake_list)
    monkeypatch.setattr(law_sync, "fetch_law", fake_fetch)
    return data


def test_sync_writes_md_and_manifest(env):
    result = law_sync.sync("dummy-oc")
    assert (env / "laws" / "법률_테스트창업법.md").exists()
    assert (env / "laws" / "대통령령_테스트창업법 시행령.md").exists()
    manifest = json.loads((env / "sources.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 2
    names = {s["name"] for s in manifest["sources"]}
    assert names == {"테스트창업법", "테스트창업법 시행령"}
    assert manifest["sources"][0]["origin"] == "law.go.kr"


def test_sync_isolates_errors(env):
    result = law_sync.sync("dummy-oc")
    # '존재하지않는법'은 목록 매칭 실패 → errors에 기록, 나머지는 정상 처리
    assert len(result["errors"]) == 1
    assert result["errors"][0]["law"] == "존재하지않는법"
    assert result["count"] == 2


def test_sync_only_filter(env):
    result = law_sync.sync("dummy-oc", only="창업")
    assert result["count"] == 2
    assert result["errors"] == []   # '존재하지않는법'은 필터로 스킵됨
