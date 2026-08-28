"""Tests for the persistent, editable plant library."""

from copy import deepcopy
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE = Path(__file__).parents[1] / "custom_components/hydroponic_system/plant_catalog.py"
SPEC = importlib.util.spec_from_file_location("plant_catalog", MODULE)
plant_catalog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plant_catalog
SPEC.loader.exec_module(plant_catalog)


def test_default_catalog_contains_global_core_crops_and_cannabis():
    catalog = plant_catalog.default_plant_catalog()

    assert catalog["schema_version"] == 5
    assert catalog["catalog_version"] == "2026.08.26"
    assert set(catalog["records"]) >= {
        "tomato", "lettuce", "cannabis", "basil", "strawberry", "pepper", "cucumber"
    }
    assert catalog["records"]["cannabis"]["botanical_name"] == "Cannabis sativa L."
    assert "Marijuana" in catalog["records"]["cannabis"]["aliases"]
    assert catalog["records"]["tomato"]["profile"]["kind"] == "editable_example"
    assert set(catalog["breeders"]) >= {
        "royal_queen_seeds", "barneys_farm", "amnesia_seeds"
    }
    cannabis = catalog["records"]["cannabis"]
    cultivars = cannabis["cultivars"]
    assert len(cultivars) == 249
    assert len({item["id"] for item in cultivars}) == 249
    assert Counter(item["growth_type"] for item in cultivars) == {
        "photoperiod": 143,
        "autoflower": 106,
    }
    assert Counter(item["breeder_id"] for item in cultivars) == {
        "barneys_farm": 83,
        "dutch_passion": 76,
        "royal_queen_seeds": 56,
        "fast_buds": 19,
        "sensi_seeds": 15,
    }
    assert all(item["reference_url"].startswith("https://") for item in cultivars)
    assert {item["id"] for item in cannabis["growth_types"]} == {
        "photoperiod", "autoflower"
    }
    assert any(
        item["name"] == "Northern Light Auto"
        and item["breeder_id"] == "royal_queen_seeds"
        and item["growth_type"] == "autoflower"
        for item in cannabis["cultivars"]
    )
    assert any(
        item["name"] == "Purple Haze"
        and item["breeder_id"] == "barneys_farm"
        for item in cannabis["cultivars"]
    )


def test_catalog_migration_preserves_edits_and_adds_missing_defaults():
    catalog = plant_catalog.normalize_plant_catalog(
        {
            "records": {
                "tomato": {"name": "Benim domatesim"},
                "my_plant": {"name": "Özel ürün", "profile": {"stages": {}}},
            },
            "order": ["my_plant", "tomato"],
        }
    )

    assert catalog["records"]["tomato"]["name"] == "Benim domatesim"
    assert catalog["records"]["my_plant"]["built_in"] is False
    assert "lettuce" in catalog["records"]
    assert catalog["order"][:2] == ["my_plant", "tomato"]
    assert catalog["schema_version"] == 5
    assert catalog["catalog_version"] == "2026.08.26"
    assert catalog["breeders"]["royal_queen_seeds"]["name"] == "Royal Queen Seeds"
    assert len(catalog["records"]["cannabis"]["cultivars"]) == 249


def test_catalog_upgrade_preserves_builtin_edits_and_adds_new_offerings():
    cannabis = deepcopy(plant_catalog.DEFAULT_PLANTS["cannabis"])
    edited = next(
        item for item in cannabis["cultivars"]
        if item["id"] == "rqs_northern_light_auto"
    )
    edited["name"] = "Benim Northern Light Auto kaydım"
    edited["active"] = False
    cannabis["cultivars"] = [edited]

    catalog = plant_catalog.normalize_plant_catalog(
        {
            "schema_version": 2,
            "records": {"cannabis": cannabis},
        }
    )

    migrated = catalog["records"]["cannabis"]["cultivars"]
    preserved = next(
        item for item in migrated if item["id"] == "rqs_northern_light_auto"
    )
    assert preserved["name"] == "Benim Northern Light Auto kaydım"
    assert preserved["active"] is False
    assert len(migrated) == 249
    assert any(item["id"] == "fast_buds_ztrawberriez_auto" for item in migrated)


def test_catalog_preserves_custom_breeder_and_custom_cultivar():
    cannabis = deepcopy(plant_catalog.DEFAULT_PLANTS["cannabis"])
    cannabis["cultivars"].append(
        {
            "id": "local_special",
            "name": "Local Special",
            "growth_type": "photoperiod",
            "breeder_id": "local_breeder",
            "active": True,
        }
    )
    catalog = plant_catalog.normalize_plant_catalog(
        {
            "records": {"cannabis": cannabis},
            "breeders": {
                "local_breeder": {
                    "name": "Local Breeder",
                    "kind": "breeder",
                    "website": "https://example.test",
                }
            },
        }
    )

    assert catalog["breeders"]["local_breeder"]["built_in"] is False
    custom = next(
        item for item in catalog["records"]["cannabis"]["cultivars"]
        if item["id"] == "local_special"
    )
    assert custom["name"] == "Local Special"
    assert custom["built_in"] is False


def test_builtin_cultivar_can_be_disabled_without_being_deleted():
    cannabis = deepcopy(plant_catalog.DEFAULT_PLANTS["cannabis"])
    target = next(
        item for item in cannabis["cultivars"]
        if item["id"] == "rqs_northern_light_auto"
    )
    target["active"] = False

    normalized = plant_catalog.normalize_plant_record(
        cannabis,
        plant_id="cannabis",
        fallback=plant_catalog.DEFAULT_PLANTS["cannabis"],
    )

    migrated = next(
        item for item in normalized["cultivars"]
        if item["id"] == "rqs_northern_light_auto"
    )
    assert migrated["active"] is False
    assert migrated["built_in"] is True


def test_cultivation_plant_snapshot_keeps_identity_and_selected_genetics_only():
    plant = plant_catalog.DEFAULT_PLANTS["cannabis"]
    cultivar = next(
        item for item in plant["cultivars"]
        if item["id"] == "rqs_northern_light_auto"
    )

    snapshot = plant_catalog.cultivation_plant_snapshot(
        plant, cultivar, catalog_version="2026.08.26"
    )

    assert "profile" not in snapshot
    assert snapshot["cultivars"] == [cultivar]
    assert snapshot["catalog_version"] == "2026.08.26"
    assert len(json.dumps(snapshot, ensure_ascii=False).encode()) < 16_384
    assert len(plant["cultivars"]) == 249


def test_standalone_identity_catalog_contains_no_grow_targets():
    catalog = plant_catalog.default_plant_identity_catalog()

    assert catalog["identity_schema_version"] == 1
    assert all("profile" not in record for record in catalog["records"].values())


def test_profile_values_are_bounded_and_ranges_are_ordered():
    tomato = deepcopy(plant_catalog.DEFAULT_PLANTS["tomato"])
    tomato["profile"]["stages"]["veg"].update(
        {"photoperiod": 99, "humidity": -5, "ph_min": 7, "ph_max": 5, "ec_max": 99}
    )

    normalized = plant_catalog.normalize_plant_record(
        tomato, plant_id="tomato", fallback=plant_catalog.DEFAULT_PLANTS["tomato"]
    )
    stage = normalized["profile"]["stages"]["veg"]
    assert stage["photoperiod"] == 24
    assert stage["humidity"] == 0
    assert (stage["ph_min"], stage["ph_max"]) == (5, 7)
    assert stage["ec_max"] == 10


def test_legacy_nutrient_products_are_removed_from_plant_profiles():
    tomato = deepcopy(plant_catalog.DEFAULT_PLANTS["tomato"])
    tomato["profile"]["stages"]["veg"]["nutrient_ids"] = [
        "tomato_grow_a", "tomato_grow_b", "tomato_grow_a",
    ]

    normalized = plant_catalog.normalize_plant_record(
        tomato, plant_id="tomato", fallback=plant_catalog.DEFAULT_PLANTS["tomato"]
    )

    assert "nutrient_ids" not in normalized["profile"]["stages"]["veg"]
    assert all(
        "nutrient_ids" not in stage
        for stage in normalized["profile"]["stages"].values()
    )


def test_plant_plan_uses_only_enabled_stages_and_is_copy_safe():
    lettuce = deepcopy(plant_catalog.DEFAULT_PLANTS["lettuce"])
    plan = plant_catalog.plant_plan(lettuce)

    assert [item["stage"] for item in plan] == [
        "germination", "early_veg", "veg", "harvest"
    ]
    plan[0]["planned_days"] = 300
    assert lettuce["profile"]["stages"]["germination"]["planned_days"] == 4


def test_invalid_custom_id_is_rejected():
    with pytest.raises(ValueError):
        plant_catalog.make_custom_plant_record("../../bad", "Bad")
