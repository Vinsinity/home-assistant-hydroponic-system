"""Versioned, editable plant library for cultivation-specific grow profiles.

The built-in profiles are deliberately labelled as starting examples.  They are
not control recipes and are copied into a cultivation so later library edits do
not rewrite historical grow context.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re
from typing import Any
import unicodedata


PLANT_CATALOG_SCHEMA_VERSION = 5
STAGE_ORDER = ("germination", "early_veg", "veg", "bloom", "darkness", "harvest")
PROFILE_KIND = "editable_example"

OKLAHOMA_HYDROPONICS_REFERENCE = (
    "https://extension.okstate.edu/fact-sheets/"
    "electrical-conductivity-and-ph-guide-for-hydroponics"
)
CANNABIS_HYDROPONICS_REFERENCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC7424260/"
CANNABIS_PHOTOPERIOD_REFERENCE = "https://ask.ifas.ufl.edu/publication/HS1452"

DEFAULT_BREEDERS: dict[str, dict[str, Any]] = {
    "royal_queen_seeds": {
        "id": "royal_queen_seeds",
        "name": "Royal Queen Seeds",
        "kind": "breeder_seed_bank",
        "website": "https://www.royalqueenseeds.com/",
        "aliases": ["RQS"],
        "built_in": True,
    },
    "barneys_farm": {
        "id": "barneys_farm",
        "name": "Barney's Farm",
        "kind": "breeder_seed_bank",
        "website": "https://www.barneysfarm.com/",
        "aliases": ["Barneys Farm", "Barney’s Farm"],
        "built_in": True,
    },
    "amnesia_seeds": {
        "id": "amnesia_seeds",
        "name": "Amnesia Seeds",
        "kind": "seed_bank",
        "website": "https://amnesiaseeds.com/",
        "aliases": [],
        "built_in": True,
    },
    "dutch_passion": {
        "id": "dutch_passion",
        "name": "Dutch Passion",
        "kind": "breeder_seed_bank",
        "website": "https://dutch-passion.com/",
        "aliases": [],
        "built_in": True,
    },
    "sensi_seeds": {
        "id": "sensi_seeds",
        "name": "Sensi Seeds",
        "kind": "breeder_seed_bank",
        "website": "https://sensiseeds.com/",
        "aliases": [],
        "built_in": True,
    },
    "fast_buds": {
        "id": "fast_buds",
        "name": "Fast Buds",
        "kind": "breeder_seed_bank",
        "website": "https://2fast4buds.com/",
        "aliases": ["2 Fast 4 Buds", "FastBuds"],
        "built_in": True,
    },
}

CANNABIS_GROWTH_TYPES = [
    {
        "id": "photoperiod",
        "name": "Photoperiod",
        "description": "Çiçeklenme ışık programındaki değişime bağlıdır.",
        "built_in": True,
    },
    {
        "id": "autoflower",
        "name": "Autoflower",
        "description": "Çiçeklenme ışık programından bağımsız olarak yaşla ilerler.",
        "built_in": True,
    },
]

_CANNABIS_CATALOG_PATH = Path(__file__).with_name("data") / "cannabis_catalog.json"


def _catalog_slug(value: str) -> str:
    """Create a stable ASCII id fragment from an official cultivar name."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")


def _load_cannabis_catalog() -> tuple[str, list[dict[str, Any]]]:
    """Load and expand the source-controlled official catalog snapshot."""
    with _CANNABIS_CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        data = json.load(catalog_file)
    cultivars: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source in data.get("sources", []):
        breeder_id = str(source.get("breeder_id", "")).strip()
        prefix = str(source.get("id_prefix", breeder_id)).strip()
        references = source.get("reference_urls", {})
        for growth_type in ("photoperiod", "autoflower"):
            reference_url = str(references.get(growth_type, "")).strip()
            for raw_name in source.get(growth_type, []):
                name = str(raw_name).strip()
                cultivar_id = f"{prefix}_{_catalog_slug(name)}"[:64].rstrip("_")
                if not name or not cultivar_id or cultivar_id in seen_ids:
                    continue
                seen_ids.add(cultivar_id)
                cultivars.append(
                    {
                        "id": cultivar_id,
                        "name": name,
                        "growth_type": growth_type,
                        "breeder_id": breeder_id,
                        "reference_url": reference_url,
                        "aliases": [],
                        "active": True,
                        "built_in": True,
                    }
                )
    return str(data.get("catalog_version", "unknown")), cultivars


CANNABIS_CATALOG_VERSION, CANNABIS_CULTIVARS = _load_cannabis_catalog()

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _text(value: Any, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if not math.isfinite(result):
        result = default
    return round(max(minimum, min(maximum, result)), 3)


def _integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    return max(minimum, min(maximum, result))


def _enabled(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return value is True or str(value).lower() in {"1", "true", "yes", "on"}


def _stage(
    *,
    enabled: bool = True,
    planned_days: int,
    photoperiod: float,
    light_intensity: float,
    day_temperature: float,
    night_temperature: float,
    humidity: float,
    vpd: float,
    co2: float = 450,
    ph_min: float,
    ph_max: float,
    ec_min: float,
    ec_max: float,
    water_temperature: float = 19,
    do_minimum: float = 6,
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "planned_days": planned_days,
        "photoperiod": photoperiod,
        "light_intensity": light_intensity,
        "day_temperature": day_temperature,
        "night_temperature": night_temperature,
        "humidity": humidity,
        "vpd": vpd,
        "co2": co2,
        "ph_min": ph_min,
        "ph_max": ph_max,
        "ec_min": ec_min,
        "ec_max": ec_max,
        "water_temperature": water_temperature,
        "do_minimum": do_minimum,
    }


def _stages(
    *,
    ph: tuple[float, float],
    ec: tuple[float, float],
    germination_days: int,
    early_days: int,
    veg_days: int,
    bloom_days: int,
    veg_photoperiod: float = 16,
    bloom_photoperiod: float = 14,
    bloom_enabled: bool = True,
    harvest_days: int = 1,
) -> dict[str, dict[str, Any]]:
    return {
        "germination": _stage(
            planned_days=germination_days, photoperiod=16, light_intensity=30,
            day_temperature=24, night_temperature=21, humidity=72, vpd=0.7,
            ph_min=ph[0], ph_max=ph[1], ec_min=max(0.2, ec[0] * 0.4),
            ec_max=max(0.4, ec[0] * 0.7),
        ),
        "early_veg": _stage(
            planned_days=early_days, photoperiod=veg_photoperiod, light_intensity=50,
            day_temperature=24, night_temperature=21, humidity=66, vpd=0.9,
            ph_min=ph[0], ph_max=ph[1], ec_min=max(0.4, ec[0] * 0.7), ec_max=ec[0],
        ),
        "veg": _stage(
            planned_days=veg_days, photoperiod=veg_photoperiod, light_intensity=75,
            day_temperature=24, night_temperature=20, humidity=60, vpd=1.1,
            ph_min=ph[0], ph_max=ph[1], ec_min=ec[0], ec_max=ec[1],
        ),
        "bloom": _stage(
            enabled=bloom_enabled, planned_days=bloom_days,
            photoperiod=bloom_photoperiod, light_intensity=90,
            day_temperature=24, night_temperature=20, humidity=55, vpd=1.2,
            ph_min=ph[0], ph_max=ph[1], ec_min=ec[0], ec_max=ec[1],
        ),
        "darkness": _stage(
            enabled=False, planned_days=1, photoperiod=0, light_intensity=0,
            day_temperature=20, night_temperature=19, humidity=55, vpd=1.0,
            ph_min=0, ph_max=0, ec_min=0, ec_max=0,
            water_temperature=0, do_minimum=0,
        ),
        "harvest": _stage(
            planned_days=harvest_days, photoperiod=0, light_intensity=0,
            day_temperature=20, night_temperature=18, humidity=55, vpd=1.0,
            ph_min=0, ph_max=0, ec_min=0, ec_max=0,
            water_temperature=0, do_minimum=0,
        ),
    }


def _plant(
    plant_id: str,
    name: str,
    english_name: str,
    botanical_name: str,
    category: str,
    cultivars: list[str],
    stages: dict[str, dict[str, Any]],
    *,
    references: list[str] | None = None,
    notes: str = "",
    aliases: list[str] | None = None,
    growth_types: list[dict[str, Any]] | None = None,
    cultivar_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": plant_id,
        "name": name,
        "english_name": english_name,
        "botanical_name": botanical_name,
        "category": category,
        "cultivar_examples": cultivars,
        "growth_types": growth_types or [],
        "cultivars": cultivar_records or [],
        "aliases": aliases or [],
        "notes": notes,
        "built_in": True,
        "profile": {
            "kind": PROFILE_KIND,
            "stages": stages,
            "references": references or [OKLAHOMA_HYDROPONICS_REFERENCE],
        },
    }


DEFAULT_PLANTS: dict[str, dict[str, Any]] = {
    "tomato": _plant(
        "tomato", "Domates", "Tomato", "Solanum lycopersicum", "fruiting",
        ["Cherry", "Roma", "Marmande", "Beefsteak"],
        _stages(ph=(6.0, 6.5), ec=(2.0, 4.0), germination_days=7,
                early_days=14, veg_days=28, bloom_days=70),
    ),
    "lettuce": _plant(
        "lettuce", "Marul", "Lettuce", "Lactuca sativa", "leafy",
        ["Butterhead", "Romaine", "Iceberg", "Loose leaf"],
        _stages(ph=(6.0, 7.0), ec=(1.2, 1.8), germination_days=4,
                early_days=7, veg_days=28, bloom_days=1, bloom_enabled=False),
    ),
    "cannabis": _plant(
        "cannabis", "Cannabis / Marijuana", "Cannabis / Marijuana", "Cannabis sativa L.", "cannabis",
        ["Northern Light", "Northern Lights", "Purple Haze", "Amnesia Haze", "White Widow"],
        _stages(ph=(5.6, 6.0), ec=(1.0, 2.4), germination_days=5,
                early_days=14, veg_days=28, bloom_days=56,
                veg_photoperiod=18, bloom_photoperiod=12, harvest_days=10),
        references=[CANNABIS_HYDROPONICS_REFERENCE, CANNABIS_PHOTOPERIOD_REFERENCE],
        notes=(
            "Photoperiod response and nutrient demand vary materially by cultivar; "
            "review and edit every stage before relying on this example."
        ),
        aliases=["Cannabis", "Marijuana", "Kenevir", "Hemp"],
        growth_types=CANNABIS_GROWTH_TYPES,
        cultivar_records=CANNABIS_CULTIVARS,
    ),
    "basil": _plant(
        "basil", "Fesleğen", "Basil", "Ocimum basilicum", "herb",
        ["Genovese", "Thai", "Purple", "Lemon"],
        _stages(ph=(5.5, 6.0), ec=(1.0, 1.6), germination_days=7,
                early_days=7, veg_days=42, bloom_days=1, bloom_enabled=False),
    ),
    "strawberry": _plant(
        "strawberry", "Çilek", "Strawberry", "Fragaria × ananassa", "berry",
        ["Albion", "Seascape", "San Andreas", "Monterey"],
        _stages(ph=(5.8, 6.2), ec=(1.8, 2.2), germination_days=14,
                early_days=21, veg_days=28, bloom_days=70),
    ),
    "pepper": _plant(
        "pepper", "Biber", "Pepper", "Capsicum annuum", "fruiting",
        ["Bell pepper", "Jalapeño", "Cayenne", "Habanero"],
        _stages(ph=(5.5, 6.0), ec=(0.8, 1.8), germination_days=10,
                early_days=14, veg_days=35, bloom_days=70),
    ),
    "cucumber": _plant(
        "cucumber", "Salatalık", "Cucumber", "Cucumis sativus", "fruiting",
        ["English", "Persian", "Beit Alpha", "Mini"],
        _stages(ph=(5.0, 5.5), ec=(1.7, 2.0), germination_days=4,
                early_days=10, veg_days=21, bloom_days=50),
    ),
}


GENERIC_PLANT = _plant(
    "custom", "Özel bitki", "Custom plant", "", "custom", [],
    _stages(ph=(5.5, 6.5), ec=(1.0, 2.0), germination_days=7,
            early_days=14, veg_days=28, bloom_days=56),
    references=[],
    notes="Review every example target for the selected species, cultivar, and system.",
)
GENERIC_PLANT["built_in"] = False


def _normalize_stage(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = deepcopy(fallback)
    result.update(
        {
            "enabled": _enabled(value.get("enabled"), bool(fallback["enabled"])),
            "planned_days": _integer(value.get("planned_days"), fallback["planned_days"], 1, 365),
            "photoperiod": _number(value.get("photoperiod"), fallback["photoperiod"], 0, 24),
            "light_intensity": _number(value.get("light_intensity"), fallback["light_intensity"], 0, 100),
            "day_temperature": _number(value.get("day_temperature"), fallback["day_temperature"], 0, 50),
            "night_temperature": _number(value.get("night_temperature"), fallback["night_temperature"], 0, 50),
            "humidity": _number(value.get("humidity"), fallback["humidity"], 0, 100),
            "vpd": _number(value.get("vpd"), fallback["vpd"], 0, 5),
            "co2": _number(value.get("co2"), fallback["co2"], 0, 5000),
            "water_temperature": _number(value.get("water_temperature"), fallback["water_temperature"], 0, 40),
            "do_minimum": _number(value.get("do_minimum"), fallback["do_minimum"], 0, 20),
        }
    )
    for prefix, maximum in (("ph", 14), ("ec", 10)):
        low = _number(value.get(f"{prefix}_min"), fallback[f"{prefix}_min"], 0, maximum)
        high = _number(value.get(f"{prefix}_max"), fallback[f"{prefix}_max"], 0, maximum)
        result[f"{prefix}_min"], result[f"{prefix}_max"] = sorted((low, high))
    # Nutrient products are selected for one cultivation, never stored inside
    # a reusable plant/grow profile. Normalization intentionally drops legacy
    # nutrient_ids so old revisions migrate without carrying the coupling on.
    result.pop("nutrient_ids", None)
    return result


def _normalize_aliases(value: Any, fallback: Any = None) -> list[str]:
    aliases: list[str] = []
    raw_aliases = value if isinstance(value, list) else fallback
    if not isinstance(raw_aliases, list):
        return aliases
    for item in raw_aliases:
        alias = _text(item, 96)
        if alias and alias.casefold() not in {entry.casefold() for entry in aliases}:
            aliases.append(alias)
        if len(aliases) == 24:
            break
    return aliases


def normalize_breeder_record(
    value: Any, *, breeder_id: str | None = None,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one bounded breeder or seed-bank library record."""
    value = value if isinstance(value, dict) else {}
    fallback = deepcopy(fallback or {})
    raw_id = _text(breeder_id or value.get("id") or fallback.get("id"), 64).lower()
    if not _ID_PATTERN.fullmatch(raw_id):
        raise ValueError(
            "Breeder id must use lowercase letters, digits, hyphens, or underscores"
        )
    website = _text(value.get("website", fallback.get("website", "")), 500)
    if website and not website.startswith(("https://", "http://")):
        website = ""
    kind = _text(value.get("kind") or fallback.get("kind") or "breeder_seed_bank", 32)
    if kind not in {"breeder", "seed_bank", "breeder_seed_bank", "supplier"}:
        kind = "breeder_seed_bank"
    return {
        "id": raw_id,
        "name": _text(value.get("name") or fallback.get("name"), 96),
        "kind": kind,
        "website": website,
        "aliases": _normalize_aliases(
            value.get("aliases"), fallback.get("aliases", [])
        ),
        "built_in": bool(fallback.get("built_in", False)),
    }


def _normalize_growth_type(
    value: Any, *, growth_type_id: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    fallback = deepcopy(fallback or {})
    if not _ID_PATTERN.fullmatch(growth_type_id):
        raise ValueError("Invalid growth type id")
    return {
        "id": growth_type_id,
        "name": _text(value.get("name") or fallback.get("name"), 64),
        "description": _text(
            value.get("description") or fallback.get("description"), 240
        ),
        "built_in": bool(fallback.get("built_in", False)),
    }


def _normalize_cultivar(
    value: Any, *, cultivar_id: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    fallback = deepcopy(fallback or {})
    if not _ID_PATTERN.fullmatch(cultivar_id):
        raise ValueError("Invalid cultivar id")
    growth_type = _text(
        value.get("growth_type") or fallback.get("growth_type"), 64
    ).lower()
    breeder_id = _text(
        value.get("breeder_id") or fallback.get("breeder_id"), 64
    ).lower()
    if growth_type and not _ID_PATTERN.fullmatch(growth_type):
        growth_type = ""
    if breeder_id and not _ID_PATTERN.fullmatch(breeder_id):
        breeder_id = ""
    reference_url = _text(
        value.get("reference_url", fallback.get("reference_url", "")), 500
    )
    if reference_url and not reference_url.startswith(("https://", "http://")):
        reference_url = ""
    return {
        "id": cultivar_id,
        "name": _text(value.get("name") or fallback.get("name"), 96),
        "growth_type": growth_type,
        "breeder_id": breeder_id,
        "aliases": _normalize_aliases(
            value.get("aliases"), fallback.get("aliases", [])
        ),
        "reference_url": reference_url,
        "active": _enabled(value.get("active"), fallback.get("active", True)),
        "built_in": bool(fallback.get("built_in", False)),
    }


def _normalize_nested_records(
    value: Any, defaults: list[dict[str, Any]], normalizer, *, maximum: int
) -> list[dict[str, Any]]:
    incoming: dict[str, dict[str, Any]] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            item_id = _text(item.get("id"), 64).lower()
            if _ID_PATTERN.fullmatch(item_id):
                incoming[item_id] = item
    default_by_id = {str(item["id"]): item for item in defaults}
    order = [*default_by_id]
    order.extend(item_id for item_id in incoming if item_id not in default_by_id)
    result = []
    for item_id in order[:maximum]:
        fallback = default_by_id.get(item_id)
        raw = incoming.get(item_id, fallback)
        try:
            normalized = normalizer(raw, item_id, fallback)
        except ValueError:
            continue
        if normalized.get("name"):
            result.append(normalized)
    return result


def normalize_plant_record(
    value: Any, *, plant_id: str | None = None, fallback: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return one complete, bounded, editable plant record."""
    value = value if isinstance(value, dict) else {}
    fallback = deepcopy(fallback or GENERIC_PLANT)
    raw_id = _text(plant_id or value.get("id") or fallback.get("id"), 64).lower()
    if not _ID_PATTERN.fullmatch(raw_id):
        raise ValueError("Plant id must use lowercase letters, digits, hyphens, or underscores")
    profile = value.get("profile") if isinstance(value.get("profile"), dict) else {}
    fallback_profile = fallback["profile"]
    incoming_stages = profile.get("stages") if isinstance(profile.get("stages"), dict) else {}
    stages = {
        stage: _normalize_stage(incoming_stages.get(stage), fallback_profile["stages"][stage])
        for stage in STAGE_ORDER
    }
    references = []
    for item in profile.get("references", fallback_profile.get("references", [])):
        url = _text(item, 500)
        if url.startswith(("https://", "http://")) and url not in references:
            references.append(url)
        if len(references) == 8:
            break
    cultivars = []
    raw_cultivars = value.get("cultivar_examples", fallback.get("cultivar_examples", []))
    if isinstance(raw_cultivars, list):
        for item in raw_cultivars:
            cultivar = _text(item, 96)
            if cultivar and cultivar.casefold() not in {entry.casefold() for entry in cultivars}:
                cultivars.append(cultivar)
            if len(cultivars) == 24:
                break
    growth_types = _normalize_nested_records(
        value.get("growth_types"),
        fallback.get("growth_types", []),
        lambda raw, item_id, item_fallback: _normalize_growth_type(
            raw, growth_type_id=item_id, fallback=item_fallback
        ),
        maximum=16,
    )
    cultivars_structured = _normalize_nested_records(
        value.get("cultivars"),
        fallback.get("cultivars", []),
        lambda raw, item_id, item_fallback: _normalize_cultivar(
            raw, cultivar_id=item_id, fallback=item_fallback
        ),
        maximum=1000,
    )
    return {
        "id": raw_id,
        "name": _text(value.get("name") or fallback.get("name"), 96),
        "english_name": _text(value.get("english_name") or fallback.get("english_name"), 96),
        "botanical_name": _text(value.get("botanical_name") or fallback.get("botanical_name"), 160),
        "category": _text(value.get("category") or fallback.get("category") or "custom", 32),
        "cultivar_examples": cultivars,
        "growth_types": growth_types,
        "cultivars": cultivars_structured,
        "aliases": _normalize_aliases(
            value.get("aliases"), fallback.get("aliases", [])
        ),
        "notes": _text(value.get("notes") or fallback.get("notes"), 2000),
        "built_in": bool(fallback.get("built_in", False)),
        "profile": {"kind": PROFILE_KIND, "stages": stages, "references": references},
    }


def default_plant_catalog() -> dict[str, Any]:
    """Return a copy-safe initial plant library."""
    return {
        "schema_version": PLANT_CATALOG_SCHEMA_VERSION,
        "catalog_version": CANNABIS_CATALOG_VERSION,
        "order": list(DEFAULT_PLANTS),
        "records": deepcopy(DEFAULT_PLANTS),
        "breeder_order": list(DEFAULT_BREEDERS),
        "breeders": deepcopy(DEFAULT_BREEDERS),
    }


def normalize_plant_catalog(value: Any) -> dict[str, Any]:
    """Migrate a plant library, preserving edits and adding missing built-ins."""
    value = value if isinstance(value, dict) else {}
    incoming = value.get("records") if isinstance(value.get("records"), dict) else {}
    records: dict[str, dict[str, Any]] = {}
    for plant_id, default in DEFAULT_PLANTS.items():
        records[plant_id] = normalize_plant_record(
            incoming.get(plant_id), plant_id=plant_id, fallback=default
        )
    for raw_id, raw_record in incoming.items():
        plant_id = _text(raw_id, 64).lower()
        if plant_id in records or not _ID_PATTERN.fullmatch(plant_id):
            continue
        try:
            record = normalize_plant_record(raw_record, plant_id=plant_id)
        except ValueError:
            continue
        if record["name"]:
            records[plant_id] = record
    order = []
    incoming_order = value.get("order") if isinstance(value.get("order"), list) else []
    for item in incoming_order:
        plant_id = _text(item, 64).lower()
        if plant_id in records and plant_id not in order:
            order.append(plant_id)
    for plant_id in records:
        if plant_id not in order:
            order.append(plant_id)
    incoming_breeders = (
        value.get("breeders") if isinstance(value.get("breeders"), dict) else {}
    )
    breeders: dict[str, dict[str, Any]] = {}
    for breeder_id, default in DEFAULT_BREEDERS.items():
        breeders[breeder_id] = normalize_breeder_record(
            incoming_breeders.get(breeder_id),
            breeder_id=breeder_id,
            fallback=default,
        )
    for raw_id, raw_record in incoming_breeders.items():
        breeder_id = _text(raw_id, 64).lower()
        if breeder_id in breeders or not _ID_PATTERN.fullmatch(breeder_id):
            continue
        try:
            breeder = normalize_breeder_record(raw_record, breeder_id=breeder_id)
        except ValueError:
            continue
        if breeder["name"]:
            breeders[breeder_id] = breeder
    breeder_order = []
    incoming_breeder_order = (
        value.get("breeder_order")
        if isinstance(value.get("breeder_order"), list)
        else []
    )
    for item in incoming_breeder_order:
        breeder_id = _text(item, 64).lower()
        if breeder_id in breeders and breeder_id not in breeder_order:
            breeder_order.append(breeder_id)
    for breeder_id in breeders:
        if breeder_id not in breeder_order:
            breeder_order.append(breeder_id)
    return {
        "schema_version": PLANT_CATALOG_SCHEMA_VERSION,
        "catalog_version": CANNABIS_CATALOG_VERSION,
        "order": order,
        "records": records,
        "breeder_order": breeder_order,
        "breeders": breeders,
    }


def make_custom_plant_record(plant_id: str, name: str) -> dict[str, Any]:
    """Create a normalized custom record using an explicitly editable template."""
    return normalize_plant_record(
        {"id": plant_id, "name": name, "english_name": name},
        plant_id=plant_id,
        fallback=GENERIC_PLANT,
    )


def cultivation_plant_snapshot(
    record: Any, cultivar: Any = None, *, catalog_version: str = ""
) -> dict[str, Any]:
    """Copy one plant profile without embedding the full cultivar library."""
    snapshot = deepcopy(record) if isinstance(record, dict) else {}
    selected = deepcopy(cultivar) if isinstance(cultivar, dict) else None
    snapshot["cultivars"] = [selected] if selected else []
    snapshot["catalog_version"] = _text(catalog_version, 32)
    return snapshot


def plant_plan(record: Any) -> list[dict[str, Any]]:
    """Build the stage calendar plan for a selected plant profile."""
    normalized = normalize_plant_record(record)
    plan = []
    for stage in STAGE_ORDER:
        target = normalized["profile"]["stages"][stage]
        if target["enabled"]:
            days = target["planned_days"]
            plan.append(
                {
                    "stage": stage,
                    "minimum_days": max(1, days - max(1, round(days * 0.2))),
                    "maximum_days": min(365, days + max(1, round(days * 0.2))),
                    "planned_days": days,
                }
            )
    if not plan:
        raise ValueError("At least one plant stage must be enabled")
    return plan
