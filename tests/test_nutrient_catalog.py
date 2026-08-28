"""Built-in manufacturer nutrient library tests."""

from custom_components.hydroponic_system.nutrient_catalog import (
    NUTRIENT_CATALOG_VERSION,
    default_nutrient_catalog,
    nutrient_environment,
    program_matches_environment,
)


def test_catalog_has_large_official_manufacturer_coverage():
    catalog = default_nutrient_catalog()

    assert catalog["catalog_version"] == NUTRIENT_CATALOG_VERSION
    assert len(catalog["brands"]) >= 20
    assert len(catalog["products"]) >= 367
    assert {
        "advanced_nutrients", "general_hydroponics", "canna", "athena",
        "terra_aquatica", "house_and_garden", "plagron", "biobizz",
        "green_house_feeding", "mills", "grotek", "remo", "hesi",
        "dutchpro", "foxfarm", "botanicare", "emerald_harvest",
        "jacks_nutrients", "floraflex", "cyco",
    } <= set(catalog["brands"])


def test_every_catalog_product_has_identity_classification_and_source():
    catalog = default_nutrient_catalog()
    assert len(catalog["product_order"]) == len(set(catalog["product_order"]))
    for product_id, product in catalog["products"].items():
        assert product["id"] == product_id
        assert product["brand_id"] in catalog["brands"]
        assert product["name"] and product["line"] and product["description"]
        assert product["category"]
        assert product["phase"]
        assert product["medium"]
        assert product["form"] in {"liquid", "powder"}
        assert product["source_url"].startswith("https://")
        assert product["official"] is True


def test_catalog_builds_reusable_programs_without_invented_doses():
    catalog = default_nutrient_catalog()

    assert len(catalog["programs"]) >= 70
    assert len(catalog["program_order"]) == len(set(catalog["program_order"]))
    for program_id, program in catalog["programs"].items():
        assert program["id"] == program_id
        assert program["brand_id"] in catalog["brands"]
        assert program_id in catalog["brands"][program["brand_id"]]["program_ids"]
        assert program["core_product_ids"]
        assert program["dose_plan_included"] is False
        assert "doz" in program["disclaimer"].casefold()
        all_ids = set(program["core_product_ids"] + program["optional_product_ids"])
        assert all_ids <= set(catalog["products"])
        for stage in program["stages"].values():
            assert set(stage["core_product_ids"] + stage["optional_product_ids"]) <= all_ids


def test_program_variants_and_environment_matching_are_explicit():
    catalog = default_nutrient_catalog()
    programs = catalog["programs"].values()
    flora = [item for item in programs if item["brand_id"] == "general_hydroponics" and item["line"] == "FloraSeries"]
    dutchpro = [item for item in programs if item["brand_id"] == "dutchpro"]
    canna_aqua = next(item for item in programs if item["brand_id"] == "canna" and item["line"] == "CANNA AQUA")

    assert {item["variant"] for item in flora} == {"Soft / normal water", "Hard water"}
    assert len(dutchpro) == 4
    assert nutrient_environment("RDWC", "Expanded clay") == "hydro"
    assert nutrient_environment("Coco", "Coco coir") == "coco"
    assert program_matches_environment(canna_aqua, "DWC", "Water only") is True
    assert program_matches_environment(canna_aqua, "Soil", "Soil") is False
