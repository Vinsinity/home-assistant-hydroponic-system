"""Built-in manufacturer nutrient library tests."""

from custom_components.hydroponic_system.nutrient_catalog import (
    NUTRIENT_CATALOG_VERSION,
    default_nutrient_catalog,
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
