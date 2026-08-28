"""Independent, user-owned cultivation profile catalogue.

Grow profiles contain stage and environmental targets only. They do not own or
embed a plant identity, cultivar, nutrient product, dosing channel, or actuator.
"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from .const import STAGE_ORDER


GROW_PROFILE_SCHEMA_VERSION = 2
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_OKLAHOMA_REFERENCE = (
    "https://extension.okstate.edu/fact-sheets/"
    "electrical-conductivity-and-ph-guide-for-hydroponics"
)
_PHOTOPERIOD_REFERENCE = "https://ask.ifas.ufl.edu/publication/HS1452"
_LEGACY_ID_MAP = {
    "tomato_starter": "extended_fruiting",
    "lettuce_starter": "short_leaf_cycle",
    "cannabis_starter": "photoperiod_18_12",
    "basil_starter": "aromatic_leaf_cycle",
    "strawberry_starter": "cool_fruiting",
    "pepper_starter": "warm_fruiting",
    "cucumber_starter": "rapid_fruiting",
}
_LEGACY_PLANT_MAP = {
    "tomato": "extended_fruiting",
    "lettuce": "short_leaf_cycle",
    "cannabis": "photoperiod_18_12",
    "basil": "aromatic_leaf_cycle",
    "strawberry": "cool_fruiting",
    "pepper": "warm_fruiting",
    "cucumber": "rapid_fruiting",
}
_LEGACY_DEFAULT_NAMES = {
    "Domates · Başlangıç",
    "Marul · Başlangıç",
    "Cannabis / Marijuana · Başlangıç",
    "Fesleğen · Başlangıç",
    "Çilek · Başlangıç",
    "Biber · Başlangıç",
    "Salatalık · Başlangıç",
}


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
            planned_days=early_days, photoperiod=veg_photoperiod,
            light_intensity=50, day_temperature=24, night_temperature=21,
            humidity=66, vpd=0.9, ph_min=ph[0], ph_max=ph[1],
            ec_min=max(0.4, ec[0] * 0.7), ec_max=ec[0],
        ),
        "veg": _stage(
            planned_days=veg_days, photoperiod=veg_photoperiod,
            light_intensity=75, day_temperature=24, night_temperature=20,
            humidity=60, vpd=1.1, ph_min=ph[0], ph_max=ph[1],
            ec_min=ec[0], ec_max=ec[1],
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


def _profile(
    profile_id: str,
    name: str,
    stages: dict[str, dict[str, Any]],
    references: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": profile_id,
        "name": name,
        "description": (
            "Düzenlenebilir hedef örneği. Bir bitki veya besin kaydıyla "
            "bağlantısı yoktur."
        ),
        "stages": stages,
        "references": references or [_OKLAHOMA_REFERENCE],
        "starter": True,
    }


DEFAULT_GROW_PROFILES = {
    "extended_fruiting": _profile(
        "extended_fruiting", "Uzun meyve dönemi",
        _stages(ph=(6.0, 6.5), ec=(2.0, 4.0), germination_days=7,
                early_days=14, veg_days=28, bloom_days=70),
    ),
    "short_leaf_cycle": _profile(
        "short_leaf_cycle", "Kısa yaprak döngüsü",
        _stages(ph=(6.0, 7.0), ec=(1.2, 1.8), germination_days=4,
                early_days=7, veg_days=28, bloom_days=1, bloom_enabled=False),
    ),
    "photoperiod_18_12": _profile(
        "photoperiod_18_12", "Fotoperiyot 18/12 döngüsü",
        _stages(ph=(5.6, 6.0), ec=(1.0, 2.4), germination_days=5,
                early_days=14, veg_days=28, bloom_days=56,
                veg_photoperiod=18, bloom_photoperiod=12, harvest_days=10),
        [_OKLAHOMA_REFERENCE, _PHOTOPERIOD_REFERENCE],
    ),
    "aromatic_leaf_cycle": _profile(
        "aromatic_leaf_cycle", "Aromatik yaprak döngüsü",
        _stages(ph=(5.5, 6.0), ec=(1.0, 1.6), germination_days=7,
                early_days=7, veg_days=42, bloom_days=1, bloom_enabled=False),
    ),
    "cool_fruiting": _profile(
        "cool_fruiting", "Serin meyve dönemi",
        _stages(ph=(5.8, 6.2), ec=(1.8, 2.2), germination_days=14,
                early_days=21, veg_days=28, bloom_days=70),
    ),
    "warm_fruiting": _profile(
        "warm_fruiting", "Sıcak meyve dönemi",
        _stages(ph=(5.5, 6.0), ec=(0.8, 1.8), germination_days=10,
                early_days=14, veg_days=35, bloom_days=70),
    ),
    "rapid_fruiting": _profile(
        "rapid_fruiting", "Hızlı meyve dönemi",
        _stages(ph=(5.0, 5.5), ec=(1.7, 2.0), germination_days=4,
                early_days=10, veg_days=21, bloom_days=50),
    ),
}


def _normalize_stage(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = {
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
    for prefix, maximum in (("ph", 14), ("ec", 10)):
        low = _number(value.get(f"{prefix}_min"), fallback[f"{prefix}_min"], 0, maximum)
        high = _number(value.get(f"{prefix}_max"), fallback[f"{prefix}_max"], 0, maximum)
        result[f"{prefix}_min"], result[f"{prefix}_max"] = sorted((low, high))
    return result


def normalize_grow_profile_record(
    value: Any,
    *,
    profile_id: str | None = None,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one bounded profile with no plant or nutrient ownership."""
    value = value if isinstance(value, dict) else {}
    fallback = deepcopy(fallback or DEFAULT_GROW_PROFILES["extended_fruiting"])
    raw_id = _text(profile_id or value.get("id") or fallback.get("id"), 64).lower()
    if not _ID_PATTERN.fullmatch(raw_id):
        raise ValueError(
            "Profile id must use lowercase letters, digits, hyphens, or underscores"
        )
    raw_stages = value.get("stages") if isinstance(value.get("stages"), dict) else {}
    fallback_stages = fallback.get(
        "stages", DEFAULT_GROW_PROFILES["extended_fruiting"]["stages"]
    )
    stages = {
        stage: _normalize_stage(raw_stages.get(stage), fallback_stages[stage])
        for stage in STAGE_ORDER
    }
    references: list[str] = []
    raw_references = value.get("references", fallback.get("references", []))
    if isinstance(raw_references, list):
        for item in raw_references:
            url = _text(item, 500)
            if url.startswith(("https://", "http://")) and url not in references:
                references.append(url)
            if len(references) == 8:
                break
    return {
        "id": raw_id,
        "name": _text(value.get("name") or fallback.get("name"), 96),
        "description": _text(value.get("description") or fallback.get("description"), 1200),
        "stages": stages,
        "references": references,
        "starter": raw_id in DEFAULT_GROW_PROFILES,
    }


def default_grow_profile_catalog(legacy_plant_catalog: Any = None) -> dict[str, Any]:
    """Return standalone examples, optionally importing old embedded targets once."""
    records = deepcopy(DEFAULT_GROW_PROFILES)
    raw_records = (
        legacy_plant_catalog.get("records", {})
        if isinstance(legacy_plant_catalog, dict)
        else {}
    )
    for plant_id, profile_id in _LEGACY_PLANT_MAP.items():
        plant = raw_records.get(plant_id)
        embedded = plant.get("profile") if isinstance(plant, dict) else None
        if not isinstance(embedded, dict):
            continue
        migrated = deepcopy(records[profile_id])
        migrated["stages"] = embedded.get("stages", migrated["stages"])
        migrated["references"] = embedded.get("references", migrated["references"])
        records[profile_id] = normalize_grow_profile_record(
            migrated, profile_id=profile_id, fallback=records[profile_id]
        )
    return {
        "schema_version": GROW_PROFILE_SCHEMA_VERSION,
        "order": list(DEFAULT_GROW_PROFILES),
        "records": records,
    }


def normalize_grow_profile_catalog(value: Any) -> dict[str, Any]:
    """Normalize records without restoring any profile the user deleted."""
    value = value if isinstance(value, dict) else {}
    try:
        schema_version = int(value.get("schema_version") or 1)
    except (TypeError, ValueError):
        schema_version = 1
    incoming = value.get("records") if isinstance(value.get("records"), dict) else {}
    records: dict[str, dict[str, Any]] = {}
    for raw_id, raw_record in incoming.items():
        old_id = _text(raw_id, 64).lower()
        profile_id = _LEGACY_ID_MAP.get(old_id, old_id) if schema_version < 2 else old_id
        if not _ID_PATTERN.fullmatch(profile_id):
            continue
        candidate = deepcopy(raw_record) if isinstance(raw_record, dict) else {}
        if schema_version < 2 and candidate.get("name") in _LEGACY_DEFAULT_NAMES:
            candidate["name"] = DEFAULT_GROW_PROFILES[profile_id]["name"]
            candidate["description"] = DEFAULT_GROW_PROFILES[profile_id]["description"]
        try:
            record = normalize_grow_profile_record(
                candidate,
                profile_id=profile_id,
                fallback=DEFAULT_GROW_PROFILES.get(profile_id),
            )
        except ValueError:
            continue
        if record["name"]:
            records[profile_id] = record
    order: list[str] = []
    incoming_order = value.get("order") if isinstance(value.get("order"), list) else []
    for item in incoming_order:
        old_id = _text(item, 64).lower()
        profile_id = _LEGACY_ID_MAP.get(old_id, old_id) if schema_version < 2 else old_id
        if profile_id in records and profile_id not in order:
            order.append(profile_id)
    order.extend(profile_id for profile_id in records if profile_id not in order)
    return {
        "schema_version": GROW_PROFILE_SCHEMA_VERSION,
        "order": order,
        "records": records,
    }


def grow_profile_plan(record: Any) -> list[dict[str, Any]]:
    """Build a stage calendar from one independent profile."""
    profile_id = str(record.get("id") or "") if isinstance(record, dict) else ""
    normalized = normalize_grow_profile_record(record, profile_id=profile_id)
    plan = []
    for stage in STAGE_ORDER:
        target = normalized["stages"][stage]
        if not target["enabled"]:
            continue
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
        raise ValueError("En az bir profil aşaması kullanılmalıdır")
    return plan


def grow_profile_snapshot(record: Any) -> dict[str, Any]:
    """Copy one profile without linking it back to mutable library state."""
    profile_id = str(record.get("id") or "") if isinstance(record, dict) else ""
    return deepcopy(normalize_grow_profile_record(record, profile_id=profile_id))
