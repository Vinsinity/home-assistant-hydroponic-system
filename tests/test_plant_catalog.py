"""Tests for the persistent, editable plant library."""

from copy import deepcopy
import importlib.util
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

    assert catalog["schema_version"] == 1
    assert set(catalog["records"]) >= {
        "tomato", "lettuce", "cannabis", "basil", "strawberry", "pepper", "cucumber"
    }
    assert catalog["records"]["cannabis"]["botanical_name"] == "Cannabis sativa L."
    assert "Marijuana" in catalog["records"]["cannabis"]["aliases"]
    assert catalog["records"]["tomato"]["profile"]["kind"] == "editable_example"


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
