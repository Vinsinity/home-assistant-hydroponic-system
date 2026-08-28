"""Independent, user-owned cultivation profile catalogue.

Grow profiles contain stage and environmental targets only.  They do not own a
plant identity, nutrient product, dosing channel, or actuator mapping.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .plant_catalog import (
    GENERIC_PLANT,
    STAGE_ORDER,
    normalize_plant_catalog,
    normalize_plant_record,
)


GROW_PROFILE_SCHEMA_VERSION = 1
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _text(value: Any, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


def normalize_grow_profile_record(
    value: Any,
    *,
    profile_id: str | None = None,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one bounded profile with no plant or nutrient ownership."""
    value = value if isinstance(value, dict) else {}
    fallback = deepcopy(fallback or {})
    raw_id = _text(profile_id or value.get("id") or fallback.get("id"), 64).lower()
    if not _ID_PATTERN.fullmatch(raw_id):
        raise ValueError(
            "Profile id must use lowercase letters, digits, hyphens, or underscores"
        )

    fallback_plant = deepcopy(GENERIC_PLANT)
    fallback_stages = fallback.get("stages")
    if isinstance(fallback_stages, dict):
        fallback_plant["profile"]["stages"] = deepcopy(fallback_stages)
    raw_stages = value.get("stages")
    normalized_plant = normalize_plant_record(
        {
            "name": "Profile target normalizer",
            "profile": {
                "stages": raw_stages if isinstance(raw_stages, dict) else {},
            },
        },
        plant_id="profile_target_normalizer",
        fallback=fallback_plant,
    )
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
        "description": _text(
            value.get("description") or fallback.get("description"), 1200
        ),
        "stages": normalized_plant["profile"]["stages"],
        "references": references,
        "starter": bool(fallback.get("starter", value.get("starter", False))),
    }


def default_grow_profile_catalog(plant_catalog: Any = None) -> dict[str, Any]:
    """Seed editable standalone profiles from the current plant targets once."""
    plants = normalize_plant_catalog(plant_catalog)
    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for plant_id in plants.get("order", []):
        plant = plants.get("records", {}).get(plant_id)
        if not isinstance(plant, dict):
            continue
        profile_id = f"{plant_id}_starter"[:64]
        record = normalize_grow_profile_record(
            {
                "id": profile_id,
                "name": f"{plant.get('name') or plant_id} · Başlangıç",
                "description": (
                    "Düzenlenebilir başlangıç örneği. Her bitkiyle seçilebilir; "
                    "besin veya doz bilgisi içermez."
                ),
                "stages": plant.get("profile", {}).get("stages", {}),
                "references": plant.get("profile", {}).get("references", []),
                "starter": True,
            },
            profile_id=profile_id,
        )
        record["starter"] = True
        records[profile_id] = record
        order.append(profile_id)
    return {
        "schema_version": GROW_PROFILE_SCHEMA_VERSION,
        "order": order,
        "records": records,
    }


def normalize_grow_profile_catalog(value: Any) -> dict[str, Any]:
    """Normalize existing records without restoring profiles the user deleted."""
    value = value if isinstance(value, dict) else {}
    incoming = value.get("records") if isinstance(value.get("records"), dict) else {}
    records: dict[str, dict[str, Any]] = {}
    for raw_id, raw_record in incoming.items():
        profile_id = _text(raw_id, 64).lower()
        if not _ID_PATTERN.fullmatch(profile_id):
            continue
        try:
            record = normalize_grow_profile_record(raw_record, profile_id=profile_id)
        except ValueError:
            continue
        if record["name"]:
            records[profile_id] = record
    order: list[str] = []
    incoming_order = value.get("order") if isinstance(value.get("order"), list) else []
    for item in incoming_order:
        profile_id = _text(item, 64).lower()
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
