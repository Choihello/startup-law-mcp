"""collect_metrics 스냅샷 빌드·오류 격리 검증 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect_metrics as cm


def test_try_captures_errors():
    ok, err = cm._try(lambda: 42)
    assert ok == 42 and err is None
    ok, err = cm._try(lambda: 1 / 0)
    assert ok is None and "ZeroDivisionError" in err


def test_build_snapshot_shape():
    snap = cm.build_snapshot({"stars": 3}, {"skipped": "FLY_API_TOKEN 없음"})
    assert snap["repo"] == cm.REPO
    assert snap["github"] == {"stars": 3}
    assert snap["fly"] == {"skipped": "FLY_API_TOKEN 없음"}
    assert snap["captured_at"].endswith("+00:00")


def test_parse_fly_result_scalar():
    data = {"data": {"result": [{"value": [1752444000, "127.4"]}]}}
    assert cm.parse_fly_result(data) == {"http_responses_7d": 127}


def test_parse_fly_result_preserves_raw_on_empty():
    data = {"data": {"result": []}}
    out = cm.parse_fly_result(data)
    assert out["raw"] == data
    assert "note" in out


def test_fly_auth_header_variants():
    assert cm.fly_auth_header("fm2_abc") == "FlyV1 fm2_abc"
    assert cm.fly_auth_header("FlyV1 fm2_abc") == "FlyV1 fm2_abc"
    assert cm.fly_auth_header("legacy_oauth") == "Bearer legacy_oauth"
