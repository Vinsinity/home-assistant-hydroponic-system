"""Independent user-owned nutrient and dosing-liquid inventory."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


NUTRIENT_INVENTORY_SCHEMA_VERSION = 1

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_REQUIRED_PH = {
    "ph_up": ("pH+", "up"),
    "ph_down": ("pH−", "down"),
}


def _text(value: Any, maximum: int, fallback: str = "") -> str:
    return str(value if value not in (None, "") else fallback).strip()[:maximum]


def normalize_nutrient_record(
    value: Any,
    *,
    product_id: str | None = None,
    required_id: str | None = None,
) -> dict[str, Any]:
    """Normalize one owned product without linking it to a plant or profile."""
    value = value if isinstance(value, dict) else {}
    record_id = str(required_id or product_id or value.get("id") or "").strip().lower()
    if not _ID_PATTERN.fullmatch(record_id):
        raise ValueError(f"Geçersiz besin ürünü kimliği: {record_id}")
    required = record_id in _REQUIRED_PH
    default_name, direction = _REQUIRED_PH.get(record_id, (record_id, ""))
    return {
        "id": record_id,
        "name": _text(value.get("name"), 64, default_name),
        "brand": _text(value.get("brand"), 64, "Belirtilmedi"),
        "category": "ph" if required else _text(value.get("category"), 32, "other"),
        "catalog_id": _text(value.get("catalog_id"), 96),
        "line": _text(value.get("line"), 64),
        "part": _text(value.get("part"), 32),
        "npk": _text(value.get("npk"), 32),
        "phase": _text(value.get("phase"), 32),
        "medium": _text(value.get("medium"), 32),
        "ph_direction": direction if required else _text(value.get("ph_direction"), 8),
        "form": _text(value.get("form"), 24),
        "input_type": _text(value.get("input_type"), 24),
        "description": _text(value.get("description"), 480),
        "source_url": _text(value.get("source_url"), 320),
        "verified_on": _text(value.get("verified_on"), 16),
        "official": bool(value.get("official", False)),
        "required": required,
    }


def default_nutrient_inventory() -> dict[str, Any]:
    """Return the required, otherwise empty user inventory."""
    records = {
        record_id: normalize_nutrient_record({}, required_id=record_id)
        for record_id in _REQUIRED_PH
    }
    return {
        "schema_version": NUTRIENT_INVENTORY_SCHEMA_VERSION,
        "order": list(_REQUIRED_PH),
        "records": records,
    }


def normalize_nutrient_inventory(
    value: Any,
    *,
    legacy_fluids: Any = None,
) -> dict[str, Any]:
    """Normalize the independent inventory or migrate the legacy hardware list."""
    source_records: dict[str, Any] = {}
    source_order: list[str] = []
    if isinstance(value, dict) and isinstance(value.get("records"), dict):
        source_records = deepcopy(value["records"])
        source_order = [str(item) for item in value.get("order", [])]
    elif isinstance(value, dict) and isinstance(value.get("products"), list):
        for item in value["products"]:
            if isinstance(item, dict) and item.get("id"):
                source_records[str(item["id"])] = deepcopy(item)
                source_order.append(str(item["id"]))
    elif isinstance(legacy_fluids, list):
        for item in legacy_fluids:
            if isinstance(item, dict) and item.get("id"):
                source_records[str(item["id"])] = deepcopy(item)
                source_order.append(str(item["id"]))

    result = default_nutrient_inventory()
    for record_id in _REQUIRED_PH:
        result["records"][record_id] = normalize_nutrient_record(
            source_records.get(record_id), required_id=record_id
        )

    ordered_ids = [*source_order, *source_records]
    for raw_id in ordered_ids:
        record_id = str(raw_id).strip().lower()
        if record_id in result["records"]:
            continue
        raw = source_records.get(raw_id, source_records.get(record_id))
        record = normalize_nutrient_record(raw, product_id=record_id)
        result["records"][record_id] = record
        result["order"].append(record_id)
    return result


def nutrient_inventory_list(value: Any) -> list[dict[str, Any]]:
    """Return inventory records in stable display order."""
    inventory = normalize_nutrient_inventory(value)
    return [
        deepcopy(inventory["records"][record_id])
        for record_id in inventory["order"]
        if record_id in inventory["records"]
    ]
