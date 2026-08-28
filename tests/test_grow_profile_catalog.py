"""Independent grow profile catalogue regression tests."""

from copy import deepcopy

from custom_components.hydroponic_system.grow_profile_catalog import (
    default_grow_profile_catalog,
    grow_profile_plan,
    normalize_grow_profile_catalog,
    normalize_grow_profile_record,
)
from custom_components.hydroponic_system.plant_catalog import default_plant_catalog


def test_starter_profiles_are_independent_from_plants_and_nutrients():
    plants = default_plant_catalog()
    catalog = default_grow_profile_catalog(plants)

    assert len(catalog["records"]) == len(plants["records"])
    assert "tomato_starter" in catalog["records"]
    for profile in catalog["records"].values():
        assert "plant_id" not in profile
        assert "plant_profile_id" not in profile
        assert all(
            "nutrient_ids" not in target
            for target in profile["stages"].values()
        )


def test_normalization_does_not_restore_a_deleted_starter_profile():
    catalog = default_grow_profile_catalog(default_plant_catalog())
    catalog["records"].pop("tomato_starter")
    catalog["order"].remove("tomato_starter")

    normalized = normalize_grow_profile_catalog(catalog)

    assert "tomato_starter" not in normalized["records"]
    assert "tomato_starter" not in normalized["order"]


def test_profile_edit_and_copy_keep_their_own_stage_targets():
    source = default_grow_profile_catalog(default_plant_catalog())["records"][
        "lettuce_starter"
    ]
    copied = deepcopy(source)
    copied["name"] = "Kendi yaz profilim"
    copied["stages"]["veg"]["planned_days"] = 35

    normalized = normalize_grow_profile_record(
        copied, profile_id="summer_profile"
    )

    assert normalized["id"] == "summer_profile"
    assert normalized["name"] == "Kendi yaz profilim"
    assert grow_profile_plan(normalized)[2]["planned_days"] == 35
    assert source["stages"]["veg"]["planned_days"] != 35
