"""Offline data-contract checks; no models, network, or image generation."""
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).parent
HELD = {"FMAKEUP000036", "FMAKEUP000043"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_resolves_each_case_and_keeps_source_status():
    manifest = read(ROOT / "image_service_manifest.json")
    entries = manifest["items"]
    assert len(entries) == len({e["case_id"] for e in entries}) == 56
    assert len({e["suggested_asset_id"] for e in entries}) == 56
    assert manifest["generation_enabled"] is False
    for entry in entries:
        sid = entry["case_id"]
        recipe = read(ROOT / entry["recipe_file"])
        assets = read(ROOT / entry["assets_file"])
        catalog = read(ROOT / entry["catalog_file"])
        case_dir = (ROOT / entry["recipe_file"]).parent
        assert recipe["case_id"] == sid == assets[0]["image_id"]
        assert len(assets) == 1
        assert len(read(case_dir / "shots.json")) == 1
        source = read(case_dir / "source-record.json")["original_entry"]
        expected = source.get("sha256", source.get("输出sha256"))
        assert entry["sha256"] == assets[0]["sha256"] == expected
        assert recipe["case_unit"] == "single_independent_reference"
        assert entry["production_ready"] is recipe["production_ready"] is False
        assert recipe["validation"]["generation_tested"] is False
        assert assets[0]["service_url"] is entry["service_url"] is None
        assert assets[0]["package_file"] == entry["package_file"]
        assert entry["default_retrieval_eligible"] == (sid not in HELD)
        assert recipe["default_retrieval_eligible"] == (sid not in HELD)
        assert recipe["source_truth_status"] == ("ai_label_recorded" if sid in HELD else "unverified")
        assert next(x for x in catalog["cases"] if x["case_id"] == sid)["source_truth_status"] == recipe["source_truth_status"]
        for observed in recipe["observations"]:
            assert observed["evidence_type"] == "observed"
            assert observed["evidence_images"] == [sid]
        assert all(v["evidence_type"] == "proposed" for v in recipe["creative_variables"])


@pytest.mark.parametrize("gender,count", [("bride", 26), ("groom", 28)])
def test_query_excludes_held_from_default_and_filters_category(gender, count):
    script = ROOT / f"{gender}_makeup_data/scripts/query_catalog.py"

    def query(*args):
        return json.loads(subprocess.check_output([sys.executable, str(script), *args], text=True))

    all_rows = query("--limit", "100")
    assert all_rows["scope"] == "review_only"
    assert len(all_rows["cases"]) == count
    assert not HELD.intersection(x["case_id"] for x in all_rows["cases"])
    category = query("--category", "03", "--limit", "100")
    assert len(category["cases"]) == 4
    assert all(x["category_id"] == "03" for x in category["cases"])
    assert query("--id", "UNKNOWN")["total_matches"] == 0
    if gender == "bride":
        explicit = query("--id", "FMAKEUP000036")
        assert explicit["total_matches"] == 1
        assert explicit["cases"][0]["default_retrieval_eligible"] is False
        assert explicit["cases"][0]["source_truth_status"] == "ai_label_recorded"


def test_internal_links_and_no_image_payloads():
    assert len(list(ROOT.rglob("SKILL.md"))) == 72
    for path in ROOT.rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" not in target:
                assert (path.parent / target).is_file(), (path, target)
    assert not [p for p in ROOT.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".webp", ".zip"}]
    for path in ROOT.rglob("*.json"):
        assert "/Users/Admin" not in path.read_text(encoding="utf-8")


def test_pilots_are_accepted_for_data_only():
    for gender, sid in [("bride", "FMAKEUP000040"), ("groom", "MMAKEUP000036")]:
        recipe = read(ROOT / f"{gender}_makeup_data/cases/{sid}/recipe.json")
        assert recipe["validation"]["data_review"] == "user_accepted_feature_extraction"
        assert recipe["source_truth_status"] == "unverified"
        assert recipe["validation"]["generation_tested"] is False
