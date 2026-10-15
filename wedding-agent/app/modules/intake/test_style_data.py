"""Offline data handoff checks; no model, image service or runtime wiring."""

import json
import runpy
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent / "knowledge" / "wedding-style-data"


def query(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "query_catalog.py"), *args],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)


def test_bundle_integrity_and_scope():
    validate = runpy.run_path(str(ROOT / "scripts" / "validate_bundle.py"))["validate"]
    result = validate(ROOT)
    assert result["cases"] == 71
    assert result["images"] == 612
    assert result["independent_cases"] == 61
    assert result["alias_cases"] == 10
    assert result["composite_files"] == 8
    assert result["orientation_review_files"] == 2


def test_query_returns_bounded_candidates_and_explicit_alias():
    candidates = query("--primary", "02", "--limit", "3")
    assert candidates["total"] > len(candidates["results"]) == 3
    assert all(row["primary"] == "02" and row["independent_style_evidence"] for row in candidates["results"])
    alias = query("--set-id", "SET000075")
    assert alias["results"][0]["canonical_case_id"] == "SET000036"
    assert query("--primary", "08") == {"total": 0, "results": []}


def test_three_pilots_are_available_without_service_urls():
    for set_id, secondary in [("SET000022", "02-02"), ("SET000001", "04-01"), ("SET000003", "06-01")]:
        result = query("--set-id", set_id)
        assert result["total"] == 1
        assert result["results"][0]["secondary"] == secondary
        assets = json.loads((ROOT / "cases" / set_id / "assets.json").read_text(encoding="utf-8"))
        assert assets and all(asset["service_url"] is None for asset in assets)
