"""Versioned manufacturer nutrient library shared by standalone products.

The catalogue contains factual product identity and classification only.  It does
not invent feeding rates and it never enables dosing.  Label formulas can vary by
market, so NPK is included only where the manufacturer source is unambiguous.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any


NUTRIENT_CATALOG_SCHEMA_VERSION = 2
NUTRIENT_CATALOG_VERSION = "2026.08.28.3"
NUTRIENT_CATALOG_VERIFIED_ON = "2026-08-28"

_PROGRAM_STAGES = ("germination", "early_veg", "veg", "bloom", "darkness", "harvest")
_HYDRO_METHODS = {
    "rdwc", "dwc", "nft", "ebb and flow", "ebb & flow", "drip",
    "aeroponics", "aeroponic", "kratky", "hydroponic", "hydro",
}

_SLUG = re.compile(r"[^a-z0-9]+")


def _id(value: str) -> str:
    slug = _SLUG.sub("_", value.casefold()).strip("_")
    if len(slug) <= 88:
        return slug
    digest = hashlib.sha256(slug.encode()).hexdigest()[:10]
    return f"{slug[:77].rstrip('_')}_{digest}"


def _p(
    name: str,
    line: str,
    part: str,
    category: str,
    phase: str,
    medium: str,
    npk: str = "",
    form: str = "liquid",
    input_type: str = "mineral",
    description: str = "",
) -> tuple[str, ...]:
    return (name, line, part, category, phase, medium, npk, form, input_type, description)


_BRANDS: tuple[dict[str, Any], ...] = (
    {
        "id": "advanced_nutrients", "name": "Advanced Nutrients",
        "website": "https://www.advancednutrients.com/products/",
        "products": (
            _p("Sensi Grow A", "pH Perfect Sensi", "A", "base", "veg", "hydro/coco"),
            _p("Sensi Grow B", "pH Perfect Sensi", "B", "base", "veg", "hydro/coco"),
            _p("Sensi Bloom A", "pH Perfect Sensi", "A", "base", "bloom", "hydro/coco"),
            _p("Sensi Bloom B", "pH Perfect Sensi", "B", "base", "bloom", "hydro/coco"),
            _p("Connoisseur Grow A", "pH Perfect Connoisseur", "A", "base", "veg", "hydro/coco"),
            _p("Connoisseur Grow B", "pH Perfect Connoisseur", "B", "base", "veg", "hydro/coco"),
            _p("Connoisseur Bloom A", "pH Perfect Connoisseur", "A", "base", "bloom", "hydro/coco"),
            _p("Connoisseur Bloom B", "pH Perfect Connoisseur", "B", "base", "bloom", "hydro/coco"),
            _p("Grow", "pH Perfect Grow Micro Bloom", "Grow", "base", "veg", "hydro/coco"),
            _p("Micro", "pH Perfect Grow Micro Bloom", "Micro", "base", "all", "hydro/coco"),
            _p("Bloom", "pH Perfect Grow Micro Bloom", "Bloom", "base", "bloom", "hydro/coco"),
            _p("Sensi Coco Grow A", "pH Perfect Sensi Coco", "A", "base", "veg", "coco"),
            _p("Sensi Coco Grow B", "pH Perfect Sensi Coco", "B", "base", "veg", "coco"),
            _p("Sensi Coco Bloom A", "pH Perfect Sensi Coco", "A", "base", "bloom", "coco"),
            _p("Sensi Coco Bloom B", "pH Perfect Sensi Coco", "B", "base", "bloom", "coco"),
            _p("Jungle Juice Grow", "Jungle Juice", "Grow", "base", "veg", "hydro/coco"),
            _p("Jungle Juice Micro", "Jungle Juice", "Micro", "base", "all", "hydro/coco"),
            _p("Jungle Juice Bloom", "Jungle Juice", "Bloom", "base", "bloom", "hydro/coco"),
            _p("Sensi Terra Grow", "Sensi Terra", "Grow", "base", "veg", "soil"),
            _p("Sensi Terra Bloom", "Sensi Terra", "Bloom", "base", "bloom", "soil"),
            _p("Big Bud", "Performance", "", "booster", "bloom", "all", description="Çiçeklenme dönemi PK güçlendiricisi."),
            _p("Bud Ignitor", "Performance", "", "booster", "bloom", "all", description="Erken çiçek gelişimi için üretici katkısı."),
            _p("Overdrive", "Performance", "", "booster", "bloom", "all", description="Geç çiçeklenme dönemi güçlendiricisi."),
            _p("Bud Candy", "Performance", "", "supplement", "bloom", "all", description="Karbonhidrat temelli aroma ve çiçek katkısı."),
            _p("Flawless Finish", "Performance", "", "cleaner", "harvest", "all", description="Hasat öncesi bitiş/temizleme ürünü."),
            _p("Rhino Skin", "Performance", "", "supplement", "all", "all", description="Silika temelli yapısal destek."),
            _p("B-52", "Performance", "", "biostimulant", "all", "all", description="B vitamini içeren bitki desteği."),
            _p("Voodoo Juice", "Beneficials", "", "biostimulant", "early_veg", "all", input_type="biological", description="Kök bölgesi için yararlı bakteri ürünü."),
            _p("Piranha", "Beneficials", "", "biostimulant", "early_veg", "all", input_type="biological", description="Kök bölgesi için yararlı mantar ürünü."),
            _p("Tarantula", "Beneficials", "", "biostimulant", "early_veg", "all", input_type="biological", description="Kök bölgesi mikrobiyal katkısı."),
            _p("Sensizym", "Performance", "", "supplement", "all", "all", description="Enzim temelli kök bölgesi katkısı."),
            _p("Sensi Cal Mag Xtra", "Performance", "", "supplement", "all", "all", description="Kalsiyum, magnezyum ve mikro element desteği."),
            _p("Revive", "Performance", "", "supplement", "all", "all", description="Eksiklik ve stres sonrası destek ürünü."),
            _p("Big Bud Coco", "Coco", "", "booster", "bloom", "coco", description="Coco için çiçeklenme PK katkısı."),
            _p("Nirvana", "Performance", "", "biostimulant", "bloom", "all", input_type="organic"),
            _p("Bud Factor X", "Performance", "", "biostimulant", "bloom", "all"),
            _p("Ancient Earth", "OG Organics", "", "conditioner", "all", "soil", input_type="organic", description="Leonardit/humik içerikli toprak düzenleyici."),
            _p("Iguana Juice Grow", "OG Organics", "Grow", "base", "veg", "soil", input_type="organic"),
            _p("Iguana Juice Bloom", "OG Organics", "Bloom", "base", "bloom", "soil", input_type="organic"),
            _p("OG Organics Big Bud", "OG Organics", "", "booster", "bloom", "soil", input_type="organic"),
            _p("Big Bud Powder", "Water Soluble", "", "booster", "bloom", "all", form="powder"),
            _p("Bud Blood Powder", "Water Soluble", "", "booster", "bloom", "all", form="powder"),
        ),
    },
    {
        "id": "general_hydroponics", "name": "General Hydroponics",
        "website": "https://generalhydroponics.com/products",
        "products": (
            _p("FloraGro", "FloraSeries", "Grow", "base", "veg", "all", "2-1-6"),
            _p("FloraMicro", "FloraSeries", "Micro", "base", "all", "all", "5-0-1"),
            _p("FloraMicro Hardwater", "FloraSeries", "Micro", "base", "all", "hydro/coco", "2-0-1"),
            _p("FloraBloom", "FloraSeries", "Bloom", "base", "bloom", "all", "0-5-4"),
            _p("MaxiGro", "Maxi Series", "Grow", "base", "veg", "all", form="powder"),
            _p("MaxiBloom", "Maxi Series", "Bloom", "base", "bloom", "all", form="powder"),
            _p("FloraNova Grow", "FloraNova", "Grow", "base", "veg", "all"),
            _p("FloraNova Bloom", "FloraNova", "Bloom", "base", "bloom", "all"),
            _p("BioThrive Grow", "BioThrive", "Grow", "base", "veg", "soil", "4-3-3", input_type="organic"),
            _p("BioThrive Bloom", "BioThrive", "Bloom", "base", "bloom", "soil", "2-4-4", input_type="organic"),
            _p("FloraPro Grow A", "FloraPro Liquids", "A", "base", "veg", "hydro/coco"),
            _p("FloraPro Grow B", "FloraPro Liquids", "B", "base", "veg", "hydro/coco"),
            _p("FloraPro Bloom A", "FloraPro Liquids", "A", "base", "bloom", "hydro/coco"),
            _p("FloraPro Bloom B", "FloraPro Liquids", "B", "base", "bloom", "hydro/coco"),
            _p("FloraPro Late Bloom", "FloraPro Liquids", "", "booster", "bloom", "hydro/coco"),
            _p("FloraPro PK+", "FloraPro", "", "booster", "bloom", "hydro/coco"),
            _p("FloraPro FUL+", "FloraPro", "", "supplement", "all", "hydro/coco"),
            _p("CALiMAGic", "Supplements", "", "supplement", "all", "all", "1-0-0", description="Kalsiyum ve magnezyum desteği."),
            _p("Armor Si", "Supplements", "", "supplement", "all", "all", "0-0-4", description="Potasyum silikat desteği."),
            _p("RapidStart", "Supplements", "", "biostimulant", "early_veg", "all", description="Kök gelişimi katkısı."),
            _p("Floralicious Plus", "Supplements", "", "biostimulant", "all", "all"),
            _p("Diamond Nectar", "Supplements", "", "conditioner", "all", "all", description="Humik asit temelli katkı."),
            _p("FloraBlend", "Supplements", "", "biostimulant", "all", "all", input_type="organic"),
            _p("Liquid KoolBloom", "Bloom & Finish", "", "booster", "bloom", "all"),
            _p("Dry KoolBloom", "Bloom & Finish", "", "booster", "bloom", "all", form="powder"),
            _p("FloraKleen", "Cleaning", "", "cleaner", "harvest", "all"),
            _p("Pro pH Up", "pH Control", "", "ph", "all", "all", description="Besin çözeltisi pH yükseltici."),
            _p("Pro pH Down", "pH Control", "", "ph", "all", "all", description="Besin çözeltisi pH düşürücü."),
        ),
    },
    {
        "id": "canna", "name": "CANNA", "website": "https://other.canna.com/products",
        "products": (
            _p("Terra Vega", "CANNA TERRA", "Grow", "base", "veg", "soil"),
            _p("Terra Flores", "CANNA TERRA", "Bloom", "base", "bloom", "soil"),
            _p("Aqua Vega A", "CANNA AQUA", "A", "base", "veg", "hydro"),
            _p("Aqua Vega B", "CANNA AQUA", "B", "base", "veg", "hydro"),
            _p("Aqua Flores A", "CANNA AQUA", "A", "base", "bloom", "hydro"),
            _p("Aqua Flores B", "CANNA AQUA", "B", "base", "bloom", "hydro"),
            _p("Coco A", "CANNA COCO", "A", "base", "all", "coco"),
            _p("Coco B", "CANNA COCO", "B", "base", "all", "coco"),
            _p("Hydro Vega A", "CANNA HYDRO", "A", "base", "veg", "hydro"),
            _p("Hydro Vega B", "CANNA HYDRO", "B", "base", "veg", "hydro"),
            _p("Hydro Flores A", "CANNA HYDRO", "A", "base", "bloom", "hydro"),
            _p("Hydro Flores B", "CANNA HYDRO", "B", "base", "bloom", "hydro"),
            _p("RHIZOTONIC", "Additives", "", "biostimulant", "early_veg", "all", description="Kök gelişimi uyarıcısı."),
            _p("CANNAZYM", "Additives", "", "supplement", "all", "all", description="Enzim ürünü."),
            _p("CANNABOOST Accelerator", "Additives", "", "booster", "bloom", "all"),
            _p("PK 13/14", "Additives", "", "booster", "bloom", "all", "0-13-14"),
            _p("CALMAG AGENT", "Additives", "", "supplement", "all", "all"),
            _p("CANNACURE", "Additives", "", "other", "all", "all", description="Yapraktan kullanılan bitki bakım ürünü."),
            _p("BIO Vega", "BIOCANNA", "Grow", "base", "veg", "soil", input_type="organic"),
            _p("BIO Flores", "BIOCANNA", "Bloom", "base", "bloom", "soil", input_type="organic"),
            _p("BIO RHIZOTONIC", "BIOCANNA", "", "biostimulant", "early_veg", "soil", input_type="organic"),
            _p("BIO BOOST", "BIOCANNA", "", "booster", "bloom", "soil", input_type="organic"),
            _p("Mono Nitrogen", "Mono Nutrients", "N", "supplement", "all", "all"),
            _p("Mono Phosphorus", "Mono Nutrients", "P", "supplement", "bloom", "all"),
            _p("Mono Potassium", "Mono Nutrients", "K", "supplement", "all", "all"),
            _p("Mono Magnesium", "Mono Nutrients", "Mg", "supplement", "all", "all"),
            _p("Mono Calcium", "Mono Nutrients", "Ca", "supplement", "all", "all"),
            _p("Mono Iron", "Mono Nutrients", "Fe", "supplement", "all", "all"),
        ),
    },
    {
        "id": "athena", "name": "Athena", "website": "https://store.athenaag.com/",
        "products": (
            _p("Grow A", "Blended Line", "A", "base", "veg", "hydro/coco"),
            _p("Grow B", "Blended Line", "B", "base", "veg", "hydro/coco"),
            _p("Bloom A", "Blended Line", "A", "base", "bloom", "hydro/coco"),
            _p("Bloom B", "Blended Line", "B", "base", "bloom", "hydro/coco"),
            _p("CaMg", "Blended Line", "", "supplement", "all", "all"),
            _p("PK", "Blended Line", "", "booster", "bloom", "all"),
            _p("Cleanse", "Blended Line", "", "cleaner", "all", "hydro/coco"),
            _p("Pro Core", "Pro Line", "Core", "base", "all", "hydro/coco", form="powder"),
            _p("Pro Grow", "Pro Line", "Grow", "base", "veg", "hydro/coco", form="powder"),
            _p("Pro Bloom", "Pro Line", "Bloom", "base", "bloom", "hydro/coco", form="powder"),
            _p("Pro Fade", "Pro Line", "Fade", "base", "bloom", "hydro/coco", form="powder", description="Son iki haftada Pro Core yerine kullanılan düşük azotlu bitiş bileşeni."),
            _p("Pro Balance", "Pro Line", "", "ph", "all", "hydro/coco", form="powder", description="Potasyum karbonat temelli pH yükseltici/tampon."),
            _p("Stack", "Foliar", "", "biostimulant", "veg", "all", description="Yapraktan kullanılan kelp temelli canopy desteği."),
            _p("Renew", "Crop Health", "", "supplement", "all", "all"),
        ),
    },
    {
        "id": "terra_aquatica", "name": "Terra Aquatica", "website": "https://www.terraaquatica.com/products/",
        "products": (
            _p("TriPart Grow", "TriPart", "Grow", "base", "veg", "all"),
            _p("TriPart Micro Soft Water", "TriPart", "Micro", "base", "all", "all"),
            _p("TriPart Micro Hard Water", "TriPart", "Micro", "base", "all", "all"),
            _p("TriPart Bloom", "TriPart", "Bloom", "base", "bloom", "all"),
            _p("DualPart Grow Soft Water", "DualPart", "Grow", "base", "veg", "all"),
            _p("DualPart Grow Hard Water", "DualPart", "Grow", "base", "veg", "all"),
            _p("DualPart Bloom", "DualPart", "Bloom", "base", "bloom", "all"),
            _p("DualPart Coco Grow A", "DualPart Coco", "A", "base", "veg", "coco"),
            _p("DualPart Coco Grow B", "DualPart Coco", "B", "base", "veg", "coco"),
            _p("DualPart Coco Bloom A", "DualPart Coco", "A", "base", "bloom", "coco"),
            _p("DualPart Coco Bloom B", "DualPart Coco", "B", "base", "bloom", "coco"),
            _p("NovaMax Grow", "NovaMax", "Grow", "base", "veg", "all"),
            _p("NovaMax Bloom", "NovaMax", "Bloom", "base", "bloom", "all"),
            _p("DryPart Grow", "DryPart", "Grow", "base", "veg", "all", form="powder"),
            _p("DryPart Bloom", "DryPart", "Bloom", "base", "bloom", "all", form="powder"),
            _p("PermaBloom", "Mineral", "", "base", "all", "hydro"),
            _p("HyperBloom", "Mineral", "", "booster", "bloom", "all", form="powder"),
            _p("FinalPart", "Mineral", "", "booster", "harvest", "all"),
            _p("Calcium Magnesium Supplement", "Supplements", "", "supplement", "all", "all"),
            _p("Oligo Spectrum", "Supplements", "", "supplement", "all", "all"),
            _p("FlashClean", "Maintenance", "", "cleaner", "harvest", "all"),
            _p("Pro Organic Grow", "Pro Organic", "Grow", "base", "veg", "all", input_type="organic"),
            _p("Pro Organic Bloom", "Pro Organic", "Bloom", "base", "bloom", "all", input_type="organic"),
            _p("Organic DryPart Grow", "Organic DryPart", "Grow", "base", "veg", "all", form="powder", input_type="organic"),
            _p("Organic DryPart Bloom", "Organic DryPart", "Bloom", "base", "bloom", "all", form="powder", input_type="organic"),
            _p("Pro Roots", "Biostimulants", "", "biostimulant", "early_veg", "all", input_type="organic"),
            _p("Root Booster", "Biostimulants", "", "biostimulant", "early_veg", "all", input_type="organic"),
            _p("Pro Bloom", "Biostimulants", "", "biostimulant", "bloom", "all", input_type="organic"),
            _p("Bloom Booster", "Biostimulants", "", "booster", "bloom", "all", input_type="organic"),
            _p("Fulvic", "Biostimulants", "", "conditioner", "all", "all", input_type="organic"),
            _p("Seaweed", "Biostimulants", "", "biostimulant", "all", "all", input_type="organic"),
            _p("Humic", "Biostimulants", "", "conditioner", "all", "all", input_type="organic"),
            _p("Silicate", "Supplements", "", "supplement", "all", "all", form="powder"),
            _p("TrikoLogic", "Microorganisms", "", "biostimulant", "all", "all", form="powder", input_type="biological"),
            _p("TrikoLogic S", "Microorganisms", "", "biostimulant", "all", "all", form="powder", input_type="biological"),
        ),
    },
    {
        "id": "house_and_garden", "name": "House & Garden", "website": "https://house-garden.us/products/",
        "products": (
            _p("Aqua Flakes A", "Aqua Flakes", "A", "base", "all", "hydro"), _p("Aqua Flakes B", "Aqua Flakes", "B", "base", "all", "hydro"),
            _p("Cocos A", "Cocos", "A", "base", "all", "coco"), _p("Cocos B", "Cocos", "B", "base", "all", "coco"),
            _p("Soil A", "Soil", "A", "base", "all", "soil"), _p("Soil B", "Soil", "B", "base", "all", "soil"),
            _p("Bio 1-Component Soil", "Soil", "", "base", "all", "soil", input_type="organic"),
            _p("Roots Excelurator", "Additives", "", "biostimulant", "early_veg", "all"),
            _p("Multi Zen", "Additives", "", "supplement", "all", "all", description="Enzim katkısı."),
            _p("Amino Treatment", "Additives", "", "biostimulant", "all", "all"),
            _p("Algen Extract", "Additives", "", "biostimulant", "all", "all", input_type="organic"),
            _p("BUD-XL", "Additives", "", "booster", "bloom", "all"),
            _p("Top Booster", "Additives", "", "booster", "bloom", "all"),
            _p("Top Shooter", "Additives", "", "booster", "bloom", "all"),
            _p("Shooting Powder", "Additives", "", "booster", "bloom", "all", form="powder"),
            _p("Drip Clean", "Maintenance", "", "cleaner", "all", "hydro/coco"),
            _p("Magic Green", "Foliar", "", "supplement", "veg", "all"),
            _p("Nitrogen Boost", "Additives", "", "supplement", "veg", "all"),
            _p("PK 13-14", "Additives", "", "booster", "bloom", "all", "0-13-14"),
            _p("CalMag Powder", "Additives", "", "supplement", "all", "all", form="powder"),
            _p("Bloom Powder", "Commercial", "", "base", "bloom", "hydro/coco", form="powder"),
        ),
    },
    {
        "id": "plagron", "name": "Plagron", "website": "https://plagron.com/en/hobby/products",
        "products": (
            _p("Alga Grow", "100% NATURAL", "Grow", "base", "veg", "soil", input_type="organic"),
            _p("Alga Bloom", "100% NATURAL", "Bloom", "base", "bloom", "soil", input_type="organic"),
            _p("Terra Grow", "100% TERRA", "Grow", "base", "veg", "soil"), _p("Terra Bloom", "100% TERRA", "Bloom", "base", "bloom", "soil"),
            _p("Cocos A", "100% COCO", "A", "base", "all", "coco"), _p("Cocos B", "100% COCO", "B", "base", "all", "coco"),
            _p("Hydro A", "100% HYDRO", "A", "base", "all", "hydro"), _p("Hydro B", "100% HYDRO", "B", "base", "all", "hydro"),
            _p("Green Sensation", "UNIVERSAL", "", "booster", "bloom", "all"),
            _p("Power Buds", "UNIVERSAL", "", "booster", "bloom", "all"),
            _p("Power Roots", "UNIVERSAL", "", "biostimulant", "early_veg", "all"),
            _p("Hydro Roots", "UNIVERSAL", "", "biostimulant", "early_veg", "hydro/coco"),
            _p("Pure Zym", "UNIVERSAL", "", "supplement", "all", "all", description="Enzim katkısı."),
            _p("Sugar Royal", "UNIVERSAL", "", "biostimulant", "bloom", "all"),
            _p("Silic Rock", "UNIVERSAL", "", "supplement", "all", "all"),
            _p("PK 13-14", "UNIVERSAL", "", "booster", "bloom", "all", "0-13-14"),
            _p("CalMag Pro", "UNIVERSAL", "", "supplement", "all", "all"),
            _p("Vita Race", "UNIVERSAL", "", "supplement", "veg", "all"),
            _p("Start Up", "UNIVERSAL", "", "biostimulant", "early_veg", "all"),
            _p("Seedbooster Plus", "UNIVERSAL", "", "biostimulant", "germination", "all"),
            _p("Lemon Kick", "pH Control", "", "ph", "all", "all", input_type="organic"),
            _p("pH Min", "pH Control", "", "ph", "all", "all"), _p("pH Plus", "pH Control", "", "ph", "all", "all"),
        ),
    },
    {
        "id": "biobizz", "name": "Biobizz", "website": "https://biobizz.com/products/",
        "products": (
            _p("Bio·Grow", "Organic", "Grow", "base", "veg", "soil", input_type="organic"), _p("Bio·Bloom", "Organic", "Bloom", "base", "bloom", "soil", input_type="organic"),
            _p("Fish·Mix", "Organic", "", "base", "veg", "soil", input_type="organic"), _p("Top·Max", "Organic", "", "booster", "bloom", "all", input_type="organic"),
            _p("Root·Juice", "Organic", "", "biostimulant", "early_veg", "all", input_type="organic"), _p("Alg·A·Mic", "Organic", "", "biostimulant", "all", "all", input_type="organic"),
            _p("Bio·Heaven", "Organic", "", "biostimulant", "all", "all", input_type="organic"), _p("Acti·Vera", "Organic", "", "biostimulant", "all", "all", input_type="organic"),
            _p("Calmag", "Organic", "", "supplement", "all", "all", input_type="organic"), _p("Microbes", "Organic", "", "biostimulant", "all", "all", form="powder", input_type="biological"),
            _p("Bio·Up", "pH Control", "", "ph", "all", "all", input_type="organic"), _p("Bio·Down", "pH Control", "", "ph", "all", "all", input_type="organic"),
            _p("Leaf·Coat", "Plant Care", "", "other", "all", "all", input_type="organic"),
        ),
    },
    {
        "id": "green_house_feeding", "name": "Green House Feeding", "website": "https://www.greenhousefeeding.com/en/",
        "products": (
            _p("Grow", "Mineral", "", "base", "veg", "all", "21-5-10 + 2Mg + TE", form="powder"),
            _p("Short Flowering", "Mineral", "", "base", "bloom", "all", "16-6-26", form="powder"), _p("Hybrids", "Mineral", "", "base", "all", "all", "15-7-22", form="powder"),
            _p("Long Flowering", "Mineral", "", "base", "bloom", "all", "18-12-18", form="powder"), _p("Booster PK+", "Mineral", "", "booster", "bloom", "all", "0-30-27", form="powder"),
            _p("Calcium", "Mineral", "", "supplement", "all", "all", "6-0-0", form="powder"), _p("CalMag", "Mineral", "", "supplement", "all", "all", form="powder"),
            _p("BioGrow", "BioEnhancer", "Grow", "base", "veg", "soil", form="powder", input_type="organic"), _p("BioBloom", "BioEnhancer", "Bloom", "base", "bloom", "soil", form="powder", input_type="organic"),
            _p("BioEnhancer", "BioEnhancer", "", "biostimulant", "all", "all", form="powder", input_type="biological"),
        ),
    },
    {
        "id": "mills", "name": "Mills Nutrients", "website": "https://millsnutrients.com/category/products/",
        "products": (
            _p("Basis A", "Basis", "A", "base", "all", "all"), _p("Basis B", "Basis", "B", "base", "all", "all"),
            _p("Start-R", "Additives", "", "biostimulant", "early_veg", "all"), _p("C4", "Additives", "", "booster", "bloom", "all"),
            _p("Ultimate PK", "Additives", "", "booster", "bloom", "all"), _p("Vitalize", "Additives", "", "supplement", "all", "all", description="Biyoyararlanımlı silisyum desteği."),
        ),
    },
    {
        "id": "grotek", "name": "Grotek", "website": "https://www.grotek.com/products/",
        "products": (
            _p("Impact A", "Impact", "A", "base", "veg", "hydro/coco"), _p("Impact B", "Impact", "B", "base", "veg", "hydro/coco"),
            _p("Precision Grow", "Precision", "Grow", "base", "veg", "all"), _p("Precision Micro", "Precision", "Micro", "base", "all", "all"), _p("Precision Bloom", "Precision", "Bloom", "base", "bloom", "all"),
            _p("Solo-Tek Grow", "Solo-Tek", "Grow", "base", "veg", "all"), _p("Solo-Tek Bloom", "Solo-Tek", "Bloom", "base", "bloom", "all"),
            _p("Monster Grow Pro", "Monster", "", "booster", "veg", "all", form="powder"), _p("Monster Bloom", "Monster", "", "booster", "bloom", "all", form="powder"),
            _p("Monster Bloom Liquid", "Monster", "", "booster", "bloom", "all"), _p("Blossom Blaster", "Bloom", "", "booster", "bloom", "all"),
            _p("Blossom Blaster Pro", "Bloom", "", "booster", "bloom", "all"), _p("Bud Fuel", "Bloom", "", "booster", "bloom", "all"),
            _p("Bud Fuel Pro", "Bloom", "", "booster", "bloom", "all"), _p("Heavy Bud Pro", "Bloom", "", "booster", "bloom", "all"),
            _p("Cal-Max", "Supplements", "", "supplement", "all", "all"), _p("Carbo-Max", "Supplements", "", "supplement", "bloom", "all"),
            _p("Growth Booster", "Supplements", "", "booster", "veg", "all", form="powder"), _p("Pro-Silicate", "Supplements", "", "supplement", "all", "all"),
            _p("Vitamax Plus", "Supplements", "", "biostimulant", "all", "all"), _p("Vitamax Pro", "Supplements", "", "biostimulant", "all", "all"),
        ),
    },
    {
        "id": "remo", "name": "Remo Nutrients", "website": "https://www.remonutrients.com/",
        "products": (
            _p("Remo Micro", "Premium Series", "Micro", "base", "all", "all", "3-0-1"), _p("Remo Grow", "Premium Series", "Grow", "base", "veg", "all", "2-3-5"),
            _p("Remo Bloom", "Premium Series", "Bloom", "base", "bloom", "all"), _p("MagNifiCal", "Premium Series", "", "supplement", "all", "all", "3-0-0"),
            _p("VeloKelp", "Premium Series", "", "biostimulant", "all", "all", "1-1-1"), _p("Nature's Candy", "Premium Series", "", "supplement", "bloom", "all", "0-0-0"),
            _p("AstroFlower", "Premium Series", "", "booster", "bloom", "all", "0-5-14"), _p("Remo Elements", "Elements", "", "base", "all", "all", form="powder"),
        ),
    },
    {
        "id": "hesi", "name": "Hesi", "website": "https://hesi.nl/",
        "products": (
            _p("TNT Complex", "Soil", "Grow", "base", "veg", "soil"), _p("Bloom Complex", "Soil", "Bloom", "base", "bloom", "soil"),
            _p("Hydro Growth", "Hydro", "Grow", "base", "veg", "hydro"), _p("Hydro Bloom", "Hydro", "Bloom", "base", "bloom", "hydro"),
            _p("Coco", "Coco", "", "base", "all", "coco"), _p("PK 13/14", "Boosters", "", "booster", "bloom", "hydro/coco", "0-13-14"),
            _p("Phosphorus Plus", "Boosters", "", "booster", "bloom", "soil"), _p("Root Complex", "Boosters", "", "biostimulant", "early_veg", "all"),
            _p("PowerZyme", "Boosters", "", "supplement", "all", "all"), _p("SuperVit", "Boosters", "", "biostimulant", "all", "all"),
            _p("Boost", "Boosters", "", "booster", "bloom", "all"),
        ),
    },
    {
        "id": "dutchpro", "name": "Dutchpro", "website": "https://dutchpro.com/en/producten/",
        "products": (
            _p("Grow Soil Hard Water A", "Original", "A", "base", "veg", "soil"), _p("Grow Soil Hard Water B", "Original", "B", "base", "veg", "soil"),
            _p("Bloom Soil Hard Water A", "Original", "A", "base", "bloom", "soil"), _p("Bloom Soil Hard Water B", "Original", "B", "base", "bloom", "soil"),
            _p("Grow Hydro/Coco Hard Water A", "Original", "A", "base", "veg", "hydro/coco"), _p("Grow Hydro/Coco Hard Water B", "Original", "B", "base", "veg", "hydro/coco"),
            _p("Bloom Hydro/Coco Hard Water A", "Original", "A", "base", "bloom", "hydro/coco"), _p("Bloom Hydro/Coco Hard Water B", "Original", "B", "base", "bloom", "hydro/coco"),
            _p("Grow Soil RO/Soft Water A", "Original", "A", "base", "veg", "soil"), _p("Grow Soil RO/Soft Water B", "Original", "B", "base", "veg", "soil"),
            _p("Bloom Soil RO/Soft Water A", "Original", "A", "base", "bloom", "soil"), _p("Bloom Soil RO/Soft Water B", "Original", "B", "base", "bloom", "soil"),
            _p("Grow Hydro/Coco RO/Soft Water A", "Original", "A", "base", "veg", "hydro/coco"), _p("Grow Hydro/Coco RO/Soft Water B", "Original", "B", "base", "veg", "hydro/coco"),
            _p("Bloom Hydro/Coco RO/Soft Water A", "Original", "A", "base", "bloom", "hydro/coco"), _p("Bloom Hydro/Coco RO/Soft Water B", "Original", "B", "base", "bloom", "hydro/coco"),
            _p("Take Root", "Additives", "", "biostimulant", "early_veg", "all"), _p("Multi Total", "Additives", "", "supplement", "all", "all"),
            _p("Amino Strength", "Additives", "", "biostimulant", "all", "all", input_type="organic"), _p("Explode", "Additives", "", "booster", "bloom", "all"),
            _p("Silica", "Additives", "", "supplement", "all", "all"),
        ),
    },
    {
        "id": "foxfarm", "name": "FoxFarm", "website": "https://foxfarm.com/",
        "products": (
            _p("Grow Big Hydro Liquid Plant Food", "Liquid Trio", "Grow", "base", "veg", "hydro"), _p("Grow Big Liquid Plant Food", "Liquid Trio", "Grow", "base", "veg", "soil"),
            _p("Big Bloom Liquid Plant Food", "Liquid Trio", "", "base", "all", "soil", input_type="organic"), _p("Tiger Bloom Liquid Plant Food", "Liquid Trio", "Bloom", "base", "bloom", "all"),
            _p("Open Sesame", "Soluble Trio", "", "booster", "bloom", "all", form="powder"), _p("Beastie Bloomz", "Soluble Trio", "", "booster", "bloom", "all", form="powder"),
            _p("Cha Ching", "Soluble Trio", "", "booster", "bloom", "all", form="powder"), _p("Bembé", "Bush Doctor", "", "supplement", "bloom", "all", input_type="organic"),
            _p("Kangaroots", "Bush Doctor", "", "biostimulant", "early_veg", "soil", input_type="biological"), _p("Microbe Brew", "Bush Doctor", "", "biostimulant", "all", "soil", input_type="biological"),
            _p("SledgeHammer", "Bush Doctor", "", "cleaner", "harvest", "all"), _p("Cal-Mag", "Bush Doctor", "", "supplement", "all", "all"),
            _p("Wholly Mackerel", "Bush Doctor", "", "base", "veg", "soil", input_type="organic"), _p("Kelp Me Kelp You", "Bush Doctor", "", "biostimulant", "all", "all", input_type="organic"),
        ),
    },
    {
        "id": "botanicare", "name": "Botanicare", "website": "https://www.botanicare.com/category/products/",
        "products": (
            _p("Pure Blend Pro Grow", "Pure Blend Pro", "Grow", "base", "veg", "all"), _p("Pure Blend Pro Bloom", "Pure Blend Pro", "Bloom", "base", "bloom", "hydro/coco"),
            _p("Pure Blend Pro Bloom Soil", "Pure Blend Pro", "Bloom", "base", "bloom", "soil"), _p("CNS17 Grow", "CNS17", "Grow", "base", "veg", "hydro/coco"),
            _p("CNS17 Bloom", "CNS17", "Bloom", "base", "bloom", "hydro/coco"), _p("CNS17 Ripe", "CNS17", "Ripe", "base", "harvest", "hydro/coco"),
            _p("KIND Base", "KIND", "Base", "base", "all", "all"), _p("KIND Grow", "KIND", "Grow", "base", "veg", "all"), _p("KIND Bloom", "KIND", "Bloom", "base", "bloom", "all"),
            _p("Cal-Mag Plus", "Supplements", "", "supplement", "all", "all"), _p("Hydroplex", "Supplements", "", "booster", "bloom", "all"),
            _p("Liquid Karma", "Supplements", "", "biostimulant", "all", "all"), _p("Silica Blast", "Supplements", "", "supplement", "all", "all"),
            _p("Hydroguard", "Supplements", "", "biostimulant", "all", "hydro", input_type="biological"), _p("Rhizo Blast", "Supplements", "", "biostimulant", "early_veg", "all"),
            _p("Sweet Raw", "Sweet", "", "supplement", "bloom", "all"), _p("Sweet Berry", "Sweet", "", "supplement", "bloom", "all"),
            _p("Sweet Grape", "Sweet", "", "supplement", "bloom", "all"), _p("Sweet Citrus", "Sweet", "", "supplement", "bloom", "all"),
            _p("Clearex", "Maintenance", "", "cleaner", "harvest", "all"),
        ),
    },
    {
        "id": "emerald_harvest", "name": "Emerald Harvest", "website": "https://emeraldharvest.co/about/product-overview/",
        "products": (
            _p("Cali Pro Grow A", "Cali Pro", "A", "base", "veg", "hydro/coco"), _p("Cali Pro Grow B", "Cali Pro", "B", "base", "veg", "hydro/coco"),
            _p("Cali Pro Bloom A", "Cali Pro", "A", "base", "bloom", "hydro/coco"), _p("Cali Pro Bloom B", "Cali Pro", "B", "base", "bloom", "hydro/coco"),
            _p("Grow", "Grow Micro Bloom", "Grow", "base", "veg", "hydro/coco"), _p("Micro", "Grow Micro Bloom", "Micro", "base", "all", "hydro/coco"),
            _p("Bloom", "Grow Micro Bloom", "Bloom", "base", "bloom", "hydro/coco"), _p("Grow Bloom", "Dry Formula", "", "base", "all", "hydro/coco", form="powder"),
            _p("Edge", "Dry Formula", "", "base", "all", "hydro/coco", form="powder"), _p("Emerald Goddess", "Supplements", "", "biostimulant", "all", "all"),
            _p("Honey Chome", "Supplements", "", "supplement", "bloom", "all"), _p("King Kola", "Supplements", "", "booster", "bloom", "all"),
            _p("Root Wizard", "Supplements", "", "biostimulant", "early_veg", "all", input_type="biological"), _p("Cal-Mag", "Additives", "", "supplement", "all", "all"),
            _p("Sturdy Stalk", "Additives", "", "supplement", "all", "all"), _p("Hydra Clear", "Additives", "", "cleaner", "all", "hydro/coco"),
            _p("pH Up", "pH Control", "", "ph", "all", "all"), _p("pH Down", "pH Control", "", "ph", "all", "all"),
        ),
    },
    {
        "id": "jacks_nutrients", "name": "Jack's Nutrients",
        "website": "https://www.jacksnutrients.com/online-store/Jacks-Nutrients-FeED-c42781056",
        "products": (
            _p("5-12-26 Part A", "FeED", "A", "base", "all", "hydro/coco", "5-12-26", form="powder"),
            _p("12-4-16", "FeED", "", "base", "all", "all", "12-4-16", form="powder"),
            _p("15-5-20", "FeED", "", "base", "all", "all", "15-5-20", form="powder"),
            _p("10-30-20 Bloom", "FeED", "Bloom", "booster", "bloom", "all", "10-30-20", form="powder"),
            _p("15-6-17 Clone", "FeED", "Clone", "base", "early_veg", "all", "15-6-17", form="powder"),
            _p("5-50-18 UltraViolet", "FeED", "", "booster", "bloom", "all", "5-50-18", form="powder"),
            _p("7-15-30 Finish", "FeED", "Finish", "base", "harvest", "all", "7-15-30", form="powder"),
            _p("16-4-17 Hydroponic", "FeED", "", "base", "all", "hydro", "16-4-17", form="powder"),
            _p("18-8-23 Outdoor", "FeED", "", "base", "all", "soil", "18-8-23", form="powder"),
            _p("8-10-26 Strawberry Part A", "FeED", "A", "base", "all", "hydro/coco", "8-10-26", form="powder"),
            _p("6-6-26 Low Phos Part A", "FeED", "A", "base", "all", "hydro/coco", "6-6-26", form="powder"),
            _p("0-12-26 Part A", "FeED", "A", "base", "all", "hydro/coco", "0-12-26", form="powder"),
        ),
    },
    {
        "id": "floraflex", "name": "FloraFlex", "website": "https://www.floraflex.com/dry-nutrients",
        "products": (
            _p("V1", "Dry Nutrients", "Part 1", "base", "veg", "hydro/coco", "14-0-4", form="powder", description="Gelişim dönemi iki parçalı ana besininin birinci bileşeni; V2 ile kullanılır."),
            _p("V2", "Dry Nutrients", "Part 2", "base", "veg", "hydro/coco", "6-17-25", form="powder", description="Gelişim dönemi iki parçalı ana besininin ikinci bileşeni; V1 ile kullanılır."),
            _p("B1", "Dry Nutrients", "Part 1", "base", "bloom", "hydro/coco", "14-0-22", form="powder", description="Çiçeklenme dönemi iki parçalı ana besininin birinci bileşeni; B2 ile kullanılır."),
            _p("B2", "Dry Nutrients", "Part 2", "base", "bloom", "hydro/coco", "0-28-18", form="powder", description="Çiçeklenme dönemi iki parçalı ana besininin ikinci bileşeni; B1 ile kullanılır."),
            _p("Bulky B", "Dry Nutrients", "", "booster", "bloom", "hydro/coco", "0-14-38", form="powder", description="Erken ve orta çiçeklenme için suda çözünen PK güçlendiricisi."),
            _p("Full Tilt", "Dry Nutrients", "", "booster", "harvest", "hydro/coco", "0-47-35", form="powder", description="Geç çiçeklenme dönemi için suda çözünen bitiş ürünü."),
        ),
    },
    {
        "id": "cyco", "name": "Cyco", "website": "https://cycoflower.com/brochure/CYCO-brochure-english.pdf",
        "products": (
            _p("Grow A", "Platinum Series", "A", "base", "veg", "hydro/coco"),
            _p("Grow B", "Platinum Series", "B", "base", "veg", "hydro/coco"),
            _p("Bloom A", "Platinum Series", "A", "base", "bloom", "hydro/coco"),
            _p("Bloom B", "Platinum Series", "B", "base", "bloom", "hydro/coco"),
            _p("B1 Boost", "Platinum Series", "", "supplement", "all", "all", "2-1-4", description="B1 vitamini ve potasyum içeren gelişim/çiçeklenme katkısı."),
            _p("Uptake", "Platinum Series", "", "conditioner", "all", "all"),
            _p("Zyme", "Platinum Series", "", "supplement", "all", "all", description="Kök bölgesi için enzim katkısı."),
            _p("Silica", "Platinum Series", "", "supplement", "all", "all", description="Silika temelli yapısal destek ürünü."),
            _p("Grow XL", "Platinum Series", "", "booster", "veg", "all"),
            _p("Ryzofuel", "Platinum Series", "", "biostimulant", "early_veg", "all"),
            _p("Dr. Repair", "Platinum Series", "", "supplement", "all", "all"),
            _p("Potash Plus", "Platinum Series", "", "booster", "bloom", "all"),
            _p("Suga Rush", "Platinum Series", "", "supplement", "bloom", "all"),
            _p("Supa Stiky", "Platinum Series", "", "booster", "bloom", "all"),
            _p("Swell", "Platinum Series", "", "booster", "bloom", "all"),
            _p("Kleanse", "Platinum Series", "", "cleaner", "harvest", "all"),
        ),
    },
)


def _description(name: str, category: str, phase: str, medium: str) -> str:
    category_text = {
        "base": "ana besin", "supplement": "destek ürünü", "booster": "güçlendirici",
        "biostimulant": "biyostimülan", "conditioner": "ortam düzenleyici",
        "cleaner": "sistem/bitiş ürünü", "ph": "pH düzenleyici", "other": "bitki bakım ürünü",
    }.get(category, "ürün")
    phase_text = {
        "all": "tüm döngü", "germination": "çimlenme", "early_veg": "köklenme ve erken gelişim",
        "veg": "gelişim", "bloom": "çiçeklenme", "harvest": "bitiş/hasat öncesi",
    }.get(phase, phase)
    medium_text = {
        "all": "tüm medyalar", "hydro/coco": "hidroponik ve coco", "hydro": "hidroponik",
        "coco": "coco", "soil": "toprak",
    }.get(medium, medium)
    return f"{name}; üretici tarafından {phase_text} için sunulan {category_text}. Uyum: {medium_text}."


def nutrient_environment(growing_method: Any, growing_medium: Any) -> str:
    """Map the user's cultivation setup to one stable nutrient environment."""
    method = str(growing_method or "").strip().casefold()
    medium = str(growing_medium or "").strip().casefold()
    if "coco" in method or "coco" in medium:
        return "coco"
    if "soil" in method or "toprak" in method or "soil" in medium or "toprak" in medium:
        return "soil"
    if method in _HYDRO_METHODS or any(
        marker in medium
        for marker in ("water", "su", "clay", "kil", "rockwool", "taş yünü", "perlite", "perlit")
    ):
        return "hydro"
    return "universal"


def program_matches_environment(
    program: dict[str, Any], growing_method: Any, growing_medium: Any
) -> bool:
    """Return whether a catalogue program can be suggested for the setup."""
    environment = nutrient_environment(growing_method, growing_medium)
    supported = program.get("supported_environments", [])
    return "universal" in supported or environment == "universal" or environment in supported


def _medium_class(value: str) -> str:
    return {
        "all": "universal",
        "hydro/coco": "hydro_coco",
        "hydro": "hydro",
        "coco": "coco",
        "soil": "soil",
    }.get(value, "universal")


def _supported_environments(medium_class: str) -> list[str]:
    return {
        "universal": ["universal"],
        "hydro_coco": ["hydro", "coco"],
        "hydro": ["hydro"],
        "coco": ["coco"],
        "soil": ["soil"],
    }[medium_class]


def _phase_product_ids(products: list[dict[str, Any]], stage: str) -> list[str]:
    phases = {
        "germination": {"germination"},
        "early_veg": {"all", "early_veg", "veg"},
        "veg": {"all", "veg"},
        "bloom": {"all", "bloom"},
        "darkness": set(),
        "harvest": {"harvest"},
    }[stage]
    return [item["id"] for item in products if item.get("phase") in phases]


def _program_variants(
    brand_id: str, line: str, base_products: list[dict[str, Any]]
) -> list[tuple[str, str, list[dict[str, Any]], str]]:
    """Split product alternatives that share one manufacturer line."""
    by_name = {item["name"]: item for item in base_products}
    explicit: dict[tuple[str, str], tuple[tuple[str, str, tuple[str, ...], str], ...]] = {
        ("general_hydroponics", "FloraSeries"): (
            ("soft_water", "Soft / normal water", ("FloraGro", "FloraMicro", "FloraBloom"), "universal"),
            ("hard_water", "Hard water", ("FloraGro", "FloraMicro Hardwater", "FloraBloom"), "hydro_coco"),
        ),
        ("terra_aquatica", "TriPart"): (
            ("soft_water", "Soft water", ("TriPart Grow", "TriPart Micro Soft Water", "TriPart Bloom"), "universal"),
            ("hard_water", "Hard water", ("TriPart Grow", "TriPart Micro Hard Water", "TriPart Bloom"), "universal"),
        ),
        ("terra_aquatica", "DualPart"): (
            ("soft_water", "Soft water", ("DualPart Grow Soft Water", "DualPart Bloom"), "universal"),
            ("hard_water", "Hard water", ("DualPart Grow Hard Water", "DualPart Bloom"), "universal"),
        ),
        ("dutchpro", "Original"): (
            ("soil_hard", "Soil · hard water", ("Grow Soil Hard Water A", "Grow Soil Hard Water B", "Bloom Soil Hard Water A", "Bloom Soil Hard Water B"), "soil"),
            ("soil_soft", "Soil · RO/soft water", ("Grow Soil RO/Soft Water A", "Grow Soil RO/Soft Water B", "Bloom Soil RO/Soft Water A", "Bloom Soil RO/Soft Water B"), "soil"),
            ("hydro_hard", "Hydro/Coco · hard water", ("Grow Hydro/Coco Hard Water A", "Grow Hydro/Coco Hard Water B", "Bloom Hydro/Coco Hard Water A", "Bloom Hydro/Coco Hard Water B"), "hydro_coco"),
            ("hydro_soft", "Hydro/Coco · RO/soft water", ("Grow Hydro/Coco RO/Soft Water A", "Grow Hydro/Coco RO/Soft Water B", "Bloom Hydro/Coco RO/Soft Water A", "Bloom Hydro/Coco RO/Soft Water B"), "hydro_coco"),
        ),
        ("green_house_feeding", "Mineral"): (
            ("hybrids", "Hybrids", ("Hybrids",), "universal"),
            ("short_flowering", "Grow + Short Flowering", ("Grow", "Short Flowering"), "universal"),
            ("long_flowering", "Grow + Long Flowering", ("Grow", "Long Flowering"), "universal"),
        ),
        ("foxfarm", "Liquid Trio"): (
            ("hydro", "Hydro", ("Grow Big Hydro Liquid Plant Food", "Tiger Bloom Liquid Plant Food"), "hydro"),
            ("soil", "Soil", ("Grow Big Liquid Plant Food", "Big Bloom Liquid Plant Food", "Tiger Bloom Liquid Plant Food"), "soil"),
        ),
        ("botanicare", "Pure Blend Pro"): (
            ("hydro_coco", "Hydro/Coco", ("Pure Blend Pro Grow", "Pure Blend Pro Bloom"), "hydro_coco"),
            ("soil", "Soil", ("Pure Blend Pro Grow", "Pure Blend Pro Bloom Soil"), "soil"),
        ),
        ("house_and_garden", "Soil"): (
            ("ab", "Soil A/B", ("Soil A", "Soil B"), "soil"),
            ("bio_one_part", "Bio 1-Component", ("Bio 1-Component Soil",), "soil"),
        ),
    }
    configured = explicit.get((brand_id, line))
    if configured:
        result = []
        for suffix, label, names, medium_class in configured:
            selected = [by_name[name] for name in names if name in by_name]
            if selected:
                result.append((suffix, label, selected, medium_class))
        return result

    if brand_id == "jacks_nutrients" and line == "FeED":
        return [
            (_id(item["name"]), item["name"], [item], _medium_class(item["medium"]))
            for item in base_products
        ]

    shared = [item for item in base_products if item.get("medium") == "all"]
    specific = sorted({item.get("medium") for item in base_products if item.get("medium") != "all"})
    if not specific:
        return [("standard", "", base_products, "universal")]
    variants = []
    for medium in specific:
        selected_specific = [item for item in base_products if item.get("medium") == medium]
        specific_parts = {item.get("part") for item in selected_specific if item.get("part")}
        selected_shared = [item for item in shared if not item.get("part") or item.get("part") not in specific_parts]
        variants.append((_id(str(medium)), "", selected_shared + selected_specific, _medium_class(str(medium))))
    return variants


def _build_programs(
    brands: dict[str, dict[str, Any]], products: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    programs: dict[str, dict[str, Any]] = {}
    program_order: list[str] = []
    for brand_id, brand in brands.items():
        base_by_line: dict[str, list[dict[str, Any]]] = {}
        brand_products = [products[item] for item in brand["product_ids"]]
        for product in brand_products:
            if product.get("category") == "base":
                base_by_line.setdefault(str(product.get("line") or "Base"), []).append(product)
        brand_program_ids: list[str] = []
        for line, base_products in base_by_line.items():
            for suffix, variant_label, core_products, medium_class in _program_variants(
                brand_id, line, base_products
            ):
                program_id = _id(f"program {brand_id} {line} {suffix}")
                supported = _supported_environments(medium_class)
                optional_products = [
                    item for item in brand_products
                    if item.get("category") not in {"base", "ph"}
                    and (
                        item.get("medium") == "all"
                        or _medium_class(str(item.get("medium"))) == medium_class
                        or medium_class == "hydro_coco" and item.get("medium") in {"hydro", "coco", "hydro/coco"}
                    )
                ]
                core_ids = [item["id"] for item in core_products]
                optional_ids = [item["id"] for item in optional_products]
                active_phases = {item.get("phase") for item in core_products}
                complete_cycle = "all" in active_phases or ({"veg", "bloom"} <= active_phases)
                if any("Part A" in item.get("name", "") for item in core_products) and not any(
                    "Part B" in item.get("name", "") for item in core_products
                ):
                    complete_cycle = False
                display_name = line + (f" · {variant_label}" if variant_label else "")
                stages = {}
                for stage in _PROGRAM_STAGES:
                    stages[stage] = {
                        "core_product_ids": _phase_product_ids(core_products, stage),
                        "optional_product_ids": _phase_product_ids(optional_products, stage),
                    }
                programs[program_id] = {
                    "id": program_id,
                    "brand_id": brand_id,
                    "brand": brand["name"],
                    "name": display_name,
                    "line": line,
                    "variant": variant_label,
                    "profile_kind": "catalog_product_profile",
                    "medium_class": medium_class,
                    "supported_environments": supported,
                    "cycle_coverage": "complete" if complete_cycle else "stage_specific",
                    "core_product_ids": core_ids,
                    "optional_product_ids": optional_ids,
                    "stages": stages,
                    "dose_plan_included": False,
                    "source_url": brand["website"],
                    "verified_on": NUTRIENT_CATALOG_VERIFIED_ON,
                    "disclaimer": "Ürün setidir; doz oranı değildir. Üretici çizelgesi, su ve bitki koşullarına göre doğrulanmalıdır.",
                }
                program_order.append(program_id)
                brand_program_ids.append(program_id)
        brand["program_ids"] = brand_program_ids
    return programs, program_order


def default_nutrient_catalog() -> dict[str, Any]:
    """Return a fresh, deterministic copy of the built-in manufacturer library."""
    brands: dict[str, dict[str, Any]] = {}
    products: dict[str, dict[str, Any]] = {}
    brand_order: list[str] = []
    product_order: list[str] = []
    for brand in _BRANDS:
        brand_id = brand["id"]
        brand_order.append(brand_id)
        product_ids: list[str] = []
        for row in brand["products"]:
            name, line, part, category, phase, medium, npk, form, input_type, detail = row
            product_id = _id(f"{brand_id} {line} {name} {part}")
            if product_id in products:
                raise RuntimeError(f"Duplicate nutrient catalogue id: {product_id}")
            product = {
                "id": product_id,
                "brand_id": brand_id,
                "brand": brand["name"],
                "name": name,
                "line": line,
                "part": part,
                "category": category,
                "phase": phase,
                "medium": medium,
                "npk": npk,
                "form": form,
                "input_type": input_type,
                "description": detail or _description(name, category, phase, medium),
                "source_url": brand["website"],
                "verified_on": NUTRIENT_CATALOG_VERIFIED_ON,
                "official": True,
            }
            products[product_id] = product
            product_order.append(product_id)
            product_ids.append(product_id)
        brands[brand_id] = {
            "id": brand_id,
            "name": brand["name"],
            "website": brand["website"],
            "product_ids": product_ids,
            "verified_on": NUTRIENT_CATALOG_VERIFIED_ON,
        }
    programs, program_order = _build_programs(brands, products)
    return deepcopy({
        "schema_version": NUTRIENT_CATALOG_SCHEMA_VERSION,
        "catalog_version": NUTRIENT_CATALOG_VERSION,
        "verified_on": NUTRIENT_CATALOG_VERIFIED_ON,
        "brand_order": brand_order,
        "brands": brands,
        "product_order": product_order,
        "products": products,
        "program_order": program_order,
        "programs": programs,
    })
