"""Versioned, append-only cultivation journal primitives.

This module deliberately has no Home Assistant imports so migrations and journal
invariants can be tested without starting Home Assistant.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4


JOURNAL_SCHEMA_VERSION = 6

EVENT_TYPES = frozenset(
    {
        "cultivation_started",
        "cultivation_finished",
        "stage_transition",
        "user_note",
        "water_added",
        "water_changed",
        "nutrient_dose",
        "ph_dose",
        "reservoir_volume",
        "calibration",
        "maintenance",
        "photo",
        "alarm",
        "ai_recommendation",
        "ai_decision",
        "legacy_import",
    }
)

USER_EVENT_TYPES = frozenset(
    {
        "user_note",
        "water_added",
        "water_changed",
        "nutrient_dose",
        "ph_dose",
        "reservoir_volume",
        "calibration",
        "maintenance",
        "photo",
    }
)

AMOUNT_EVENT_UNITS = {
    "water_added": "L",
    "water_changed": "L",
    "nutrient_dose": "ml",
    "ph_dose": "ml",
    "reservoir_volume": "L",
}

IDENTITY_DEFAULTS: dict[str, Any] = {
    "plant_profile_id": "",
    "plant_species": "",
    "botanical_name": "",
    "cultivar": "",
    "cultivar_id": "",
    "growth_type": "",
    "breeder_id": "",
    "breeder_name": "",
    "source": "",
    "plant_count": 1,
    "growing_method": "RDWC",
    "growing_medium": "",
    "reservoir_volume_l": 0.0,
    "system_volume_l": 0.0,
    "photoperiod": "profile",
    "nutrient_program": "",
    "notes": "",
}


def utc_now() -> str:
    """Return a stable UTC timestamp for persisted journal data."""
    return datetime.now(timezone.utc).isoformat()


def empty_cultivations() -> dict[str, Any]:
    """Return the empty v2 cultivation collection."""
    return {"active_id": None, "order": [], "records": {}}


def empty_cultivation_view() -> dict[str, Any]:
    """Return the compatibility view expected by the current panel."""
    return {
        "active": False,
        "id": "",
        "name": "",
        "identity": deepcopy(IDENTITY_DEFAULTS),
        "system_snapshot": {},
        "plant_profile_snapshot": {},
        "genetics_snapshot": {},
        "nutrient_program_snapshot": {},
        "start_date": "",
        "started_at": "",
        "completed_at": "",
        "plan": [],
        "transitions": [],
    }


def normalize_identity(value: Any) -> dict[str, Any]:
    """Validate and bound the identity fields stored with one cultivation."""
    value = value if isinstance(value, dict) else {}
    result = deepcopy(IDENTITY_DEFAULTS)
    for key, maximum in (
        ("plant_profile_id", 64),
        ("plant_species", 96),
        ("botanical_name", 160),
        ("cultivar", 96),
        ("cultivar_id", 64),
        ("growth_type", 64),
        ("breeder_id", 64),
        ("breeder_name", 96),
        ("source", 160),
        ("growing_method", 64),
        ("growing_medium", 96),
        ("photoperiod", 64),
        ("nutrient_program", 160),
        ("notes", 4000),
    ):
        result[key] = str(value.get(key) or result[key])[:maximum]
    try:
        plant_count = int(value.get("plant_count", 1))
    except (TypeError, ValueError):
        plant_count = 1
    result["plant_count"] = max(1, min(10000, plant_count))
    for key in ("reservoir_volume_l", "system_volume_l"):
        try:
            volume = float(value.get(key, 0))
        except (TypeError, ValueError):
            volume = 0.0
        result[key] = round(max(0.0, min(100000.0, volume)), 3)
    return result


def validate_local_date(value: str) -> str:
    """Validate and return an ISO local calendar date."""
    return date.fromisoformat(str(value)).isoformat()


def _bounded_json(
    value: Any, maximum_bytes: int | None = 16_384
) -> dict[str, Any]:
    """Return a JSON-safe bounded event payload."""
    if not isinstance(value, dict):
        raise ValueError("Event data must be an object")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if maximum_bytes is not None and len(encoded.encode("utf-8")) > maximum_bytes:
        raise ValueError("Event data is too large")
    return json.loads(encoded)


def normalize_user_event_values(event_type: str, value: Any) -> dict[str, Any]:
    """Validate the small, deterministic payload allowed for a user journal event."""
    if event_type not in USER_EVENT_TYPES:
        raise ValueError(f"Unsupported user journal event type: {event_type}")
    value = value if isinstance(value, dict) else {}
    if event_type in AMOUNT_EVENT_UNITS:
        try:
            amount = float(value.get("amount"))
        except (TypeError, ValueError) as err:
            raise ValueError("This journal event requires a numeric amount") from err
        minimum = 0.0 if event_type == "reservoir_volume" else 0.000001
        if not minimum <= amount <= 100000:
            raise ValueError("Journal event amount is outside the supported range")
        expected_unit = AMOUNT_EVENT_UNITS[event_type]
        if value.get("unit") not in {None, "", expected_unit}:
            raise ValueError(f"{event_type} must use {expected_unit}")
        return {"amount": round(amount, 4), "unit": expected_unit}
    if event_type == "photo":
        url = str(value.get("url") or "")[:2048]
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("Photo events require an http(s) URL")
        return {"url": url}
    return {}


def make_event(
    *,
    event_type: str,
    cultivation_id: str | None,
    local_date: str,
    note: str = "",
    data: dict[str, Any] | None = None,
    source: str = "system",
    severity: str = "info",
    created_by: str = "",
    event_id: str | None = None,
    created_at: str | None = None,
    maximum_data_bytes: int | None = 16_384,
) -> dict[str, Any]:
    """Create one immutable event record."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported journal event type: {event_type}")
    if severity not in {"info", "warning", "critical"}:
        raise ValueError("Event severity must be info, warning, or critical")
    if event_id is not None:
        clean_event_id = str(event_id)
        valid_id = clean_event_id.replace("-", "").replace("_", "").isalnum()
        if not clean_event_id or len(clean_event_id) > 64 or not valid_id:
            raise ValueError(
                "Event id must be 1-64 letters, digits, hyphens, or underscores"
            )
    else:
        clean_event_id = uuid4().hex
    timestamp = created_at or utc_now()
    return {
        "id": clean_event_id,
        "cultivation_id": cultivation_id,
        "type": event_type,
        "local_date": validate_local_date(local_date),
        "occurred_at": timestamp,
        "created_at": timestamp,
        "created_by": str(created_by)[:128],
        "source": str(source)[:32],
        "severity": severity,
        "note": str(note or "")[:4000],
        "data": _bounded_json(data or {}, maximum_data_bytes),
    }


def _deterministic_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]}"


def _normalize_record(record: dict[str, Any], record_id: str) -> dict[str, Any]:
    result = deepcopy(record)
    result["id"] = record_id
    result["active"] = bool(result.get("active", False))
    result["name"] = str(result.get("name") or f"Yetiştirme · {result.get('start_date', '')}")[:80]
    result["start_date"] = str(result.get("start_date") or "")[:10]
    result["started_at"] = str(result.get("started_at") or "")[:40]
    result["completed_at"] = str(result.get("completed_at") or "")[:40]
    result["created_at"] = str(result.get("created_at") or result["started_at"] or utc_now())[:40]
    updated_at = (
        result.get("updated_at")
        or result["completed_at"]
        or result["started_at"]
        or result["created_at"]
    )
    result["updated_at"] = str(updated_at)[:40]
    result["identity"] = normalize_identity(result.get("identity"))
    result["system_snapshot"] = _bounded_json(
        result.get("system_snapshot")
        if isinstance(result.get("system_snapshot"), dict)
        else {}
    )
    result["plant_profile_snapshot"] = _bounded_json(
        result.get("plant_profile_snapshot")
        if isinstance(result.get("plant_profile_snapshot"), dict)
        else {},
        maximum_bytes=65_536,
    )
    result["genetics_snapshot"] = _bounded_json(
        result.get("genetics_snapshot")
        if isinstance(result.get("genetics_snapshot"), dict)
        else {},
        maximum_bytes=16_384,
    )
    result["nutrient_program_snapshot"] = _bounded_json(
        result.get("nutrient_program_snapshot")
        if isinstance(result.get("nutrient_program_snapshot"), dict)
        else {},
        maximum_bytes=32_768,
    )
    result["plan"] = deepcopy(result.get("plan") if isinstance(result.get("plan"), list) else [])
    result["transitions"] = deepcopy(
        result.get("transitions") if isinstance(result.get("transitions"), list) else []
    )
    return result


def new_cultivation(
    *,
    name: str,
    start_date: str,
    identity: dict[str, Any],
    plan: list[dict[str, Any]],
    system_snapshot: dict[str, Any] | None = None,
    plant_profile_snapshot: dict[str, Any] | None = None,
    genetics_snapshot: dict[str, Any] | None = None,
    nutrient_program_snapshot: dict[str, Any] | None = None,
    initial_stage: str | None = None,
    cultivation_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Create a new active cultivation record."""
    start_date = validate_local_date(start_date)
    timestamp = timestamp or utc_now()
    record_id = str(cultivation_id or uuid4().hex)
    if len(record_id) > 64 or not record_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Cultivation id must be 1-64 letters, digits, hyphens, or underscores")
    enabled_stages = [str(item.get("stage") or "") for item in plan if item.get("stage")]
    initial_stage = str(initial_stage or (enabled_stages[0] if enabled_stages else "germination"))
    if enabled_stages and initial_stage not in enabled_stages:
        raise ValueError("Initial stage must be enabled in the cultivation plan")
    return {
        "active": True,
        "id": record_id,
        "name": str(name or f"Yetiştirme · {start_date}")[:80],
        "identity": normalize_identity(identity),
        "system_snapshot": _bounded_json(system_snapshot or {}),
        "plant_profile_snapshot": _bounded_json(
            plant_profile_snapshot or {}, maximum_bytes=65_536
        ),
        "genetics_snapshot": _bounded_json(
            genetics_snapshot or {}, maximum_bytes=16_384
        ),
        "nutrient_program_snapshot": _bounded_json(
            nutrient_program_snapshot or {}, maximum_bytes=32_768
        ),
        "start_date": start_date,
        "started_at": timestamp,
        "completed_at": "",
        "created_at": timestamp,
        "updated_at": timestamp,
        "plan": deepcopy(plan),
        "transitions": [{"stage": initial_stage, "date": start_date}],
    }


def active_cultivation(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active record, if the collection invariant is satisfied."""
    collection = data.get("cultivations", {})
    active_id = collection.get("active_id")
    record = collection.get("records", {}).get(active_id) if active_id else None
    return record if isinstance(record, dict) and record.get("active") else None


def append_event(data: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Append an event once; there is intentionally no update/delete operation."""
    events = data.setdefault("events", [])
    event_id = event.get("id")
    if not event_id or any(item.get("id") == event_id for item in events):
        raise ValueError("Journal event id is missing or already exists")
    events.append(deepcopy(event))
    return event


def start_cultivation(
    data: dict[str, Any], record: dict[str, Any], *, created_by: str = ""
) -> dict[str, Any]:
    """Add a cultivation without replacing any previous record."""
    if active_cultivation(data) is not None:
        raise ValueError("A cultivation is already active")
    collection = data.setdefault("cultivations", empty_cultivations())
    record_id = record["id"]
    if record_id in collection.setdefault("records", {}):
        raise ValueError("Cultivation id already exists")
    collection["records"][record_id] = deepcopy(record)
    collection.setdefault("order", []).append(record_id)
    collection["active_id"] = record_id
    initial_stage = str(
        record.get("transitions", [{}])[0].get("stage") or "germination"
    )
    data["active_stage"] = initial_stage
    append_event(
        data,
        make_event(
            event_type="cultivation_started",
            cultivation_id=record_id,
            local_date=record["start_date"],
            note=record["name"],
            data={
                "identity": record["identity"],
                "system_snapshot": record.get("system_snapshot", {}),
                "plant_profile_snapshot": record.get("plant_profile_snapshot", {}),
                "genetics_snapshot": record.get("genetics_snapshot", {}),
                "nutrient_program_snapshot": record.get("nutrient_program_snapshot", {}),
            },
            created_by=created_by,
            created_at=record["started_at"],
            maximum_data_bytes=65_536,
        ),
    )
    transition = make_event(
        event_type="stage_transition",
        cultivation_id=record_id,
        local_date=record["start_date"],
        note=initial_stage,
        data={"from_stage": None, "stage": initial_stage},
        created_by=created_by,
        created_at=record["started_at"],
    )
    append_event(data, transition)
    record_in_store = collection["records"][record_id]
    record_in_store["transitions"][0]["event_id"] = transition["id"]
    return record_in_store


def select_stage(
    data: dict[str, Any], stage: str, *, local_date: str, created_by: str = ""
) -> dict[str, Any]:
    """Record a stage transition for the active cultivation."""
    record = active_cultivation(data)
    if record is None:
        raise ValueError("A stage cannot be activated before cultivation starts")
    previous = data.get("active_stage")
    if previous == stage:
        return record
    timestamp = utc_now()
    event = make_event(
        event_type="stage_transition",
        cultivation_id=record["id"],
        local_date=local_date,
        note=stage,
        data={"from_stage": previous, "stage": stage},
        created_by=created_by,
        created_at=timestamp,
    )
    append_event(data, event)
    record.setdefault("transitions", []).append(
        {"stage": stage, "date": validate_local_date(local_date), "event_id": event["id"]}
    )
    record["updated_at"] = timestamp
    data["active_stage"] = stage
    return record


def finish_cultivation(
    data: dict[str, Any], *, local_date: str, created_by: str = ""
) -> dict[str, Any]:
    """Finish and archive the active cultivation without deleting its journal."""
    record = active_cultivation(data)
    if record is None:
        raise ValueError("There is no active cultivation")
    timestamp = utc_now()
    append_event(
        data,
        make_event(
            event_type="cultivation_finished",
            cultivation_id=record["id"],
            local_date=local_date,
            note=record["name"],
            data={"final_stage": data.get("active_stage")},
            created_by=created_by,
            created_at=timestamp,
        ),
    )
    record["active"] = False
    record["completed_at"] = timestamp
    record["updated_at"] = timestamp
    data["cultivations"]["active_id"] = None
    data["active_stage"] = None
    return record


def _legacy_journal_events(
    journal: Any, cultivation_id: str | None, origin: str
) -> list[dict[str, Any]]:
    if not isinstance(journal, dict):
        return []
    events: list[dict[str, Any]] = []
    for raw_date, entry in journal.items():
        try:
            local_date = validate_local_date(str(raw_date))
        except ValueError:
            local_date = date.today().isoformat()
        payload = {"origin": origin, "entry": deepcopy(entry)}
        event_id = _deterministic_id("legacy", [cultivation_id, raw_date, origin, entry])
        events.append(
            make_event(
                event_type="legacy_import",
                cultivation_id=cultivation_id,
                local_date=local_date,
                note="Eski günlük girdisi eksiksiz içe aktarıldı",
                data=payload,
                source="migration",
                event_id=event_id,
                created_at=f"{local_date}T00:00:00+00:00",
                maximum_data_bytes=None,
            )
        )
        if isinstance(entry, dict):
            for index, photo in enumerate(entry.get("photos", [])):
                photo_data = deepcopy(photo) if isinstance(photo, dict) else {"url": str(photo)}
                events.append(
                    make_event(
                        event_type="photo",
                        cultivation_id=cultivation_id,
                        local_date=local_date,
                        note=str(photo_data.get("caption") or "Eski günlük fotoğrafı"),
                        data=photo_data,
                        source="migration",
                        event_id=_deterministic_id(
                            "legacy_photo", [cultivation_id, raw_date, origin, index, photo]
                        ),
                        created_at=f"{local_date}T00:00:00+00:00",
                        maximum_data_bytes=None,
                    )
                )
    return events


def _legacy_lifecycle_events(
    record: dict[str, Any], cultivation_id: str
) -> list[dict[str, Any]]:
    """Turn legacy lifecycle fields into immutable events without losing fields."""
    events: list[dict[str, Any]] = []
    raw_start_date = record.get("start_date")
    try:
        start_date = validate_local_date(str(raw_start_date)) if raw_start_date else ""
    except ValueError:
        start_date = date.today().isoformat()
    if raw_start_date:
        events.append(
            make_event(
                event_type="cultivation_started",
                cultivation_id=cultivation_id,
                local_date=start_date,
                note=record.get("name", ""),
                data={"migrated": True},
                source="migration",
                event_id=_deterministic_id("legacy_start", [cultivation_id, start_date]),
                created_at=record.get("started_at") or f"{start_date}T00:00:00+00:00",
            )
        )
    previous = None
    for index, transition in enumerate(record.get("transitions", [])):
        if not isinstance(transition, dict) or not transition.get("stage"):
            continue
        raw_transition_date = transition.get("date") or start_date
        try:
            transition_date = validate_local_date(str(raw_transition_date))
        except ValueError:
            transition_date = start_date or date.today().isoformat()
        events.append(
            make_event(
                event_type="stage_transition",
                cultivation_id=cultivation_id,
                local_date=transition_date,
                note=str(transition["stage"]),
                data={
                    "from_stage": previous,
                    "stage": transition["stage"],
                    "migrated": True,
                },
                source="migration",
                event_id=_deterministic_id(
                    "legacy_stage", [cultivation_id, index, transition]
                ),
                created_at=f"{transition_date}T00:00:00+00:00",
            )
        )
        previous = transition["stage"]
    completed_at = record.get("completed_at")
    if completed_at:
        try:
            completed_date = validate_local_date(str(completed_at)[:10])
        except ValueError:
            completed_date = start_date or date.today().isoformat()
        events.append(
            make_event(
                event_type="cultivation_finished",
                cultivation_id=cultivation_id,
                local_date=completed_date,
                note=record.get("name", ""),
                data={"migrated": True},
                source="migration",
                event_id=_deterministic_id("legacy_finish", [cultivation_id, completed_at]),
                created_at=str(completed_at),
            )
        )
    return events


def migrate_journal(stored: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Migrate legacy single-cultivation data without dropping unknown journal data."""
    stored = stored if isinstance(stored, dict) else {}
    changed = stored.get("schema_version") != JOURNAL_SCHEMA_VERSION
    collection = empty_cultivations()
    events: list[dict[str, Any]] = []

    incoming_collection = stored.get("cultivations")
    if isinstance(incoming_collection, dict):
        records = incoming_collection.get("records", {})
        if isinstance(records, dict):
            for raw_id, raw_record in records.items():
                if not isinstance(raw_record, dict):
                    changed = True
                    continue
                record_id = str(raw_id)
                normalized = _normalize_record(raw_record, record_id)
                collection["records"][record_id] = normalized
                if normalized != raw_record:
                    changed = True
        order = incoming_collection.get("order", [])
        collection["order"] = [
            str(item) for item in order if str(item) in collection["records"]
        ]
        for record_id in collection["records"]:
            if record_id not in collection["order"]:
                collection["order"].append(record_id)
                changed = True
        active_id = incoming_collection.get("active_id")
        if active_id in collection["records"] and collection["records"][active_id].get("active"):
            collection["active_id"] = active_id

    for item in stored.get("events", []):
        if isinstance(item, dict) and item.get("id"):
            events.append(deepcopy(item))
        else:
            changed = True

    legacy = stored.get("cultivation")
    legacy_id: str | None = None
    if isinstance(legacy, dict) and any(
        legacy.get(key) for key in ("id", "name", "start_date", "journal", "transitions")
    ):
        legacy_id = str(legacy.get("id") or _deterministic_id("cultivation", legacy))
        if legacy_id not in collection["records"]:
            legacy_record = deepcopy(legacy)
            legacy_journal = legacy_record.pop("journal", {})
            legacy_record["legacy_journal"] = deepcopy(legacy_journal)
            collection["records"][legacy_id] = _normalize_record(legacy_record, legacy_id)
            collection["order"].append(legacy_id)
            events.extend(_legacy_lifecycle_events(collection["records"][legacy_id], legacy_id))
            events.extend(_legacy_journal_events(legacy_journal, legacy_id, "cultivation.journal"))
            changed = True
        if legacy.get("active"):
            collection["active_id"] = legacy_id

    calendar = stored.get("calendar", {})
    calendar_journal = calendar.get("journal", {}) if isinstance(calendar, dict) else {}
    if calendar_journal:
        events.extend(_legacy_journal_events(calendar_journal, legacy_id, "calendar.journal"))
        changed = True

    known_event_ids: set[str] = set()
    unique_events = []
    for event in events:
        event_id = str(event.get("id") or "")
        if not event_id or event_id in known_event_ids:
            changed = True
            continue
        known_event_ids.add(event_id)
        unique_events.append(event)

    active_candidates = [
        record_id
        for record_id, record in collection["records"].items()
        if record.get("active")
    ]
    preferred = collection.get("active_id")
    if preferred not in active_candidates:
        preferred = max(
            active_candidates,
            key=lambda item: collection["records"][item].get("updated_at", ""),
            default=None,
        )
    collection["active_id"] = preferred
    for record_id, record in collection["records"].items():
        should_be_active = record_id == preferred
        if record.get("active") != should_be_active:
            record["active"] = should_be_active
            changed = True

    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "cultivations": collection,
        "events": unique_events,
    }, changed


def merge_journal_recovery(
    primary: dict[str, Any], recovery: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Merge a redundant journal copy, preferring the newest record and every event."""
    merged = deepcopy(primary)
    changed = False
    primary_collection = merged.setdefault("cultivations", empty_cultivations())
    recovery_collection = recovery.get("cultivations", {})
    for record_id, recovery_record in recovery_collection.get("records", {}).items():
        current = primary_collection["records"].get(record_id)
        if current is None or str(recovery_record.get("updated_at", "")) > str(
            current.get("updated_at", "")
        ):
            primary_collection["records"][record_id] = deepcopy(recovery_record)
            changed = True
    for record_id in recovery_collection.get("order", []):
        if (
            record_id in primary_collection["records"]
            and record_id not in primary_collection["order"]
        ):
            primary_collection["order"].append(record_id)
            changed = True

    known = {item.get("id") for item in merged.setdefault("events", [])}
    for event in recovery.get("events", []):
        if event.get("id") not in known:
            merged["events"].append(deepcopy(event))
            known.add(event.get("id"))
            changed = True

    active_candidates = [
        record_id
        for record_id, record in primary_collection["records"].items()
        if record.get("active")
    ]
    active_id = max(
        active_candidates,
        key=lambda item: primary_collection["records"][item].get("updated_at", ""),
        default=None,
    )
    if primary_collection.get("active_id") != active_id:
        primary_collection["active_id"] = active_id
        changed = True
    for record_id, record in primary_collection["records"].items():
        if record.get("active") != (record_id == active_id):
            record["active"] = record_id == active_id
            changed = True
    merged["schema_version"] = JOURNAL_SCHEMA_VERSION
    return merged, changed


def events_for_cultivation(
    data: dict[str, Any], cultivation_id: str | None
) -> list[dict[str, Any]]:
    """Return cultivation events plus global system events in append order."""
    return [
        deepcopy(event)
        for event in data.get("events", [])
        if event.get("cultivation_id") in {None, cultivation_id}
    ]


def calendar_journal(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Project append-only events into the panel's date-indexed calendar shape."""
    journal: dict[str, dict[str, Any]] = {}
    for event in events:
        local_date = event.get("local_date")
        if not local_date:
            continue
        entry = journal.setdefault(local_date, {"events": [], "photos": []})
        entry["events"].append(deepcopy(event))
        if event.get("type") == "photo" and event.get("data", {}).get("url"):
            entry["photos"].append(
                {
                    "url": event["data"]["url"],
                    "caption": event.get("note", ""),
                    "event_id": event.get("id"),
                }
            )
    return journal


def cultivation_summaries(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return stable summaries without discarding completed cultivations."""
    collection = data.get("cultivations", {})
    counts: dict[str, int] = {}
    for event in data.get("events", []):
        cultivation_id = event.get("cultivation_id")
        if cultivation_id:
            counts[cultivation_id] = counts.get(cultivation_id, 0) + 1
    result = []
    for record_id in reversed(collection.get("order", [])):
        record = collection.get("records", {}).get(record_id)
        if not record:
            continue
        result.append(
            {
                "id": record_id,
                "active": bool(record.get("active")),
                "name": record.get("name", ""),
                "identity": deepcopy(record.get("identity", {})),
                "start_date": record.get("start_date", ""),
                "completed_at": record.get("completed_at", ""),
                "event_count": counts.get(record_id, 0),
            }
        )
    return result


def journal_checksum(payload: dict[str, Any]) -> str:
    """Return a checksum for exports and redundant recovery copies."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def is_unverified_legacy_calibration(value: Any) -> bool:
    """Identify the old synthetic 1 ml/s placeholder, never a measured result."""
    if not isinstance(value, dict) or value.get("calibrated_at"):
        return False
    try:
        return (
            float(value.get("seconds")) == 1.0
            and float(value.get("volume_ml")) == 1.0
            and int(value.get("speed")) == 100
            and float(value.get("flow_ml_s")) == 1.0
        )
    except (TypeError, ValueError):
        return False
