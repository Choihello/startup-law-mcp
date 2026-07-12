import json

import pytest

import law_search as ls
import stages as st


def test_real_stages_structure():
    if not st.STAGES_FILE.exists():
        pytest.skip("data/stages.json 없음")
    data = json.loads(st.STAGES_FILE.read_text(encoding="utf-8"))
    ids = [s["id"] for s in data["stages"]]
    assert ids == ["idea", "incorporation", "funding", "hiring", "tax", "ip"]
    for s in data["stages"]:
        assert 3 <= len(s["key_articles"]) <= 6
        assert s["summary"] and s["checklist"]
        assert all(r.get("why") for r in s["key_articles"])


def test_real_stages_articles_exist():
    if not ls.INDEX_FILE.exists():
        pytest.skip("실데이터 인덱스 없음 (CI 환경)")
    if not st.STAGES_FILE.exists():
        pytest.skip("data/stages.json 없음")
    data = json.loads(st.STAGES_FILE.read_text(encoding="utf-8"))
    missing = []
    for s in data["stages"]:
        for ref in s["key_articles"]:
            if not ls.get_article(ref["source"], ref["article"]):
                missing.append(f'{s["id"]}: {ref["source"]} {ref["article"]}')
    assert not missing, f"실재하지 않는 큐레이션 조문: {missing}"
