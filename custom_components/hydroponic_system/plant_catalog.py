"""Versioned, editable plant library for cultivation-specific grow profiles.

The built-in profiles are deliberately labelled as starting examples.  They are
not control recipes and are copied into a cultivation so later library edits do
not rewrite historical grow context.
"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any


PLANT_CATALOG_SCHEMA_VERSION = 1
STAGE_ORDER = ("germination", "early_veg", "veg", "bloom", "darkness", "harvest")
PROFILE_KIND = "editable_example"

OKLAHOMA_HYDROPONICS_REFERENCE = (
    "https://extension.okstate.edu/fact-sheets/"
    "electrical-conductivity-and-ph-guide-for-hydroponics"
)
CANNABIS_HYDROPONICS_REFERENCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC7424260/"
CANNABIS_PHOTOPERIOD_REFERENCE = "https://ask.ifas.ufl.edu/publication/HS1452"

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
) -> dict[str, Any]:
    return {
        "id": plant_id,
        "name": name,
        "english_name": english_name,
        "botanical_name": botanical_name,
        "category": category,
        "cultivar_examples": cultivars,
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
        ["Photoperiod", "Autoflower", "CBD dominant", "Northern Lights", "Blue Dream", "White Widow"],
        _stages(ph=(5.6, 6.0), ec=(1.0, 2.4), germination_days=5,
                early_days=14, veg_days=28, bloom_days=56,
                veg_photoperiod=18, bloom_photoperiod=12, harvest_days=10),
        references=[CANNABIS_HYDROPONICS_REFERENCE, CANNABIS_PHOTOPERIOD_REFERENCE],
        notes=(
            "Photoperiod response and nutrient demand vary materially by cultivar; "
            "review and edit every stage before relying on this example."
        ),
        aliases=["Cannabis", "Marijuana", "Kenevir", "Hemp"],
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
    aliases = []
    raw_aliases = value.get("aliases", fallback.get("aliases", []))
    if isinstance(raw_aliases, list):
        for item in raw_aliases:
            alias = _text(item, 96)
            if alias and alias.casefold() not in {entry.casefold() for entry in aliases}:
                aliases.append(alias)
            if len(aliases) == 24:
                break
    return {
        "id": raw_id,
        "name": _text(value.get("name") or fallback.get("name"), 96),
        "english_name": _text(value.get("english_name") or fallback.get("english_name"), 96),
        "botanical_name": _text(value.get("botanical_name") or fallback.get("botanical_name"), 160),
        "category": _text(value.get("category") or fallback.get("category") or "custom", 32),
        "cultivar_examples": cultivars,
        "aliases": aliases,
        "notes": _text(value.get("notes") or fallback.get("notes"), 2000),
        "built_in": bool(fallback.get("built_in", False)),
        "profile": {"kind": PROFILE_KIND, "stages": stages, "references": references},
    }


def default_plant_catalog() -> dict[str, Any]:
    """Return a copy-safe initial plant library."""
    return {
        "schema_version": PLANT_CATALOG_SCHEMA_VERSION,
        "order": list(DEFAULT_PLANTS),
        "records": deepcopy(DEFAULT_PLANTS),
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
    for item in value.get("order", []):
        plant_id = _text(item, 64).lower()
        if plant_id in records and plant_id not in order:
            order.append(plant_id)
    for plant_id in records:
        if plant_id not in order:
            order.append(plant_id)
    return {
        "schema_version": PLANT_CATALOG_SCHEMA_VERSION,
        "order": order,
        "records": records,
    }


def make_custom_plant_record(plant_id: str, name: str) -> dict[str, Any]:
    """Create a normalized custom record using an explicitly editable template."""
    return normalize_plant_record(
        {"id": plant_id, "name": name, "english_name": name},
        plant_id=plant_id,
        fallback=GENERIC_PLANT,
    )


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
