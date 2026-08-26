"""Persistent configuration plus redundant append-only cultivation journal."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_DOSING_POLICY,
    DEFAULT_PROFILES,
    JOURNAL_RECOVERY_STORAGE_KEY,
    JOURNAL_RECOVERY_STORAGE_VERSION,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .grow_profile import (
    DEFAULT_ASSISTANT_SETTINGS,
    DEFAULT_SYSTEM_PROFILE,
    normalize_assistant_settings,
    normalize_system_profile,
)
from .journal import (
    JOURNAL_SCHEMA_VERSION,
    active_cultivation,
    append_event,
    calendar_journal,
    cultivation_summaries,
    empty_cultivations,
    events_for_cultivation,
    finish_cultivation,
    is_unverified_legacy_calibration,
    journal_checksum,
    make_event,
    merge_journal_recovery,
    migrate_journal,
    normalize_user_event_values,
    select_stage,
    start_cultivation,
    utc_now,
)
from .plant_catalog import (
    GENERIC_PLANT,
    default_plant_catalog,
    make_custom_plant_record,
    normalize_breeder_record,
    normalize_plant_catalog,
    normalize_plant_record,
)


class HydroponicSystemStore:
    """Store settings and mirror the irreplaceable journal into a recovery file."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._journal_recovery_store: Store[dict[str, Any]] = Store(
            hass,
            JOURNAL_RECOVERY_STORAGE_VERSION,
            JOURNAL_RECOVERY_STORAGE_KEY,
        )
        self.data: dict[str, Any] = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "active_stage": None,
            "engine_enabled": False,
            "profiles": deepcopy(DEFAULT_PROFILES),
            "system_profile": deepcopy(DEFAULT_SYSTEM_PROFILE),
            "assistant_settings": deepcopy(DEFAULT_ASSISTANT_SETTINGS),
            "plant_catalog": default_plant_catalog(),
            "cultivations": empty_cultivations(),
            "events": [],
            "hardware": {
                "i2c_bus": 1,
                "poll_interval": 30,
                "dosing_policy": deepcopy(DEFAULT_DOSING_POLICY),
                "device_assignments": [],
                "dosing_fluids": [
                    {"id": "ph_up", "name": "pH+", "required": True},
                    {"id": "ph_down", "name": "pH−", "required": True},
                ],
            },
        }
        self.journal_diagnostic: dict[str, Any] = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "mirrored": False,
            "recovered": False,
            "recovery_error": None,
        }

    async def async_load(self) -> None:
        """Load persisted data and merge new default fields."""
        stored = await self._store.async_load() or {}
        recovery = await self._journal_recovery_store.async_load() or {}
        migrated = not bool(stored)
        self.data["active_stage"] = stored.get("active_stage")
        self.data["engine_enabled"] = stored.get("engine_enabled", False)
        self.data["system_profile"] = normalize_system_profile(
            stored.get("system_profile")
        )
        self.data["assistant_settings"] = normalize_assistant_settings(
            stored.get("assistant_settings")
        )
        self.data["plant_catalog"] = normalize_plant_catalog(
            stored.get("plant_catalog")
        )
        if (
            self.data["system_profile"] != stored.get("system_profile")
            or self.data["assistant_settings"] != stored.get("assistant_settings")
            or self.data["plant_catalog"] != stored.get("plant_catalog")
        ):
            migrated = True
        stored_profiles = stored.get("profiles", {})
        for stage, defaults in DEFAULT_PROFILES.items():
            self.data["profiles"][stage].update(stored_profiles.get(stage, {}))
            # Profile names are canonical UI labels, not user data. Refresh old
            # persisted English labels without changing stable internal keys.
            if self.data["profiles"][stage].get("name") != defaults["name"]:
                self.data["profiles"][stage]["name"] = defaults["name"]
                migrated = True
            if stage not in stored_profiles or any(
                key not in stored_profiles.get(stage, {}) for key in defaults
            ):
                migrated = True
        self.data["hardware"].update(stored.get("hardware", {}))
        policy = self.data["hardware"].setdefault("dosing_policy", {})
        for key, value in DEFAULT_DOSING_POLICY.items():
            if key not in policy:
                policy[key] = value
                migrated = True
        # Version 0.24.9 wrote a synthetic 1 ml/s placeholder. It must never be
        # interpreted as a physical calibration or enable future dosing.
        for assignment in self.data["hardware"].get("device_assignments", []):
            if assignment.get("driver") != "waveshare_motor_hat":
                continue
            for channel in assignment.get("channels", []):
                calibration = channel.get("calibration")
                if is_unverified_legacy_calibration(calibration):
                    channel["calibration"] = None
                    channel["calibration_status"] = "unverified"
                    migrated = True
                elif calibration:
                    if channel.get("calibration_status") != "measured":
                        channel["calibration_status"] = "measured"
                        migrated = True
                elif channel.get("calibration_status") != "unverified":
                    channel["calibration_status"] = "unverified"
                    migrated = True

        journal, journal_migrated = migrate_journal(stored)
        self.data.update(journal)
        migrated = migrated or journal_migrated

        recovery_payload = recovery.get("payload")
        if isinstance(recovery_payload, dict):
            expected = recovery.get("checksum")
            if expected and expected == journal_checksum(recovery_payload):
                recovery_journal, recovery_migrated = migrate_journal(
                    recovery_payload
                )
                merged, recovered = merge_journal_recovery(
                    journal, recovery_journal
                )
                self.data.update(merged)
                self.journal_diagnostic["mirrored"] = True
                self.journal_diagnostic["recovered"] = recovered
                migrated = migrated or recovery_migrated or recovered
            else:
                self.journal_diagnostic["recovery_error"] = "Recovery checksum mismatch"
                migrated = True
        else:
            migrated = True

        cultivation = active_cultivation(self.data)
        if cultivation is None:
            if self.data.get("active_stage") is not None:
                migrated = True
            self.data["active_stage"] = None
        else:
            transitions = cultivation.get("transitions", [])
            expected_stage = (
                transitions[-1].get("stage") if transitions else "germination"
            )
            if self.data.get("active_stage") != expected_stage:
                self.data["active_stage"] = expected_stage
                migrated = True
        if migrated:
            await self.async_save()

    async def async_save(self) -> None:
        """Persist current data."""
        payload = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "cultivations": deepcopy(self.data.get("cultivations", empty_cultivations())),
            "events": deepcopy(self.data.get("events", [])),
        }
        await self._journal_recovery_store.async_save(
            {
                "saved_at": utc_now(),
                "checksum": journal_checksum(payload),
                "payload": payload,
            }
        )
        self.journal_diagnostic["mirrored"] = True
        self.journal_diagnostic["recovery_error"] = None
        await self._store.async_save(self.data)

    @property
    def active_cultivation(self) -> dict[str, Any] | None:
        """Return the active cultivation without exposing a mutable fallback."""
        return active_cultivation(self.data)

    def active_calendar(self) -> dict[str, Any]:
        """Build the current cultivation's append-only calendar projection."""
        active = self.active_cultivation
        events = events_for_cultivation(self.data, active.get("id") if active else None)
        return {"journal": calendar_journal(events)}

    def cultivation_history(self) -> list[dict[str, Any]]:
        """Return active and archived cultivation summaries."""
        return cultivation_summaries(self.data)

    async def async_start_cultivation(
        self, record: dict[str, Any], *, created_by: str = ""
    ) -> dict[str, Any]:
        """Start one cultivation without replacing any prior record."""
        result = start_cultivation(self.data, record, created_by=created_by)
        await self.async_save()
        return result

    async def async_select_stage(
        self, stage: str, *, local_date: str, created_by: str = ""
    ) -> dict[str, Any]:
        """Persist an append-only stage transition."""
        result = select_stage(self.data, stage, local_date=local_date, created_by=created_by)
        await self.async_save()
        return result

    async def async_finish_cultivation(
        self, *, local_date: str, created_by: str = ""
    ) -> dict[str, Any]:
        """Archive the current cultivation and retain every event."""
        result = finish_cultivation(self.data, local_date=local_date, created_by=created_by)
        await self.async_save()
        return result

    async def async_append_event(
        self,
        *,
        event_type: str,
        local_date: str,
        note: str,
        values: dict[str, Any],
        created_by: str = "",
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a user event to the active cultivation; never update or delete."""
        cultivation = self.active_cultivation
        if cultivation is None:
            raise ValueError("There is no active cultivation")
        if event_type != "photo" and not str(note).strip():
            raise ValueError("A journal note is required")
        if event_id:
            existing = next(
                (item for item in self.data.get("events", []) if item.get("id") == event_id),
                None,
            )
            if existing is not None:
                if existing.get("cultivation_id") != cultivation["id"]:
                    raise ValueError("Journal event id belongs to another cultivation")
                await self.async_save()
                return deepcopy(existing)
        event = make_event(
            event_type=event_type,
            cultivation_id=cultivation["id"],
            local_date=local_date,
            note=note,
            data=normalize_user_event_values(event_type, values),
            source="user",
            created_by=created_by,
            event_id=event_id,
        )
        from .journal import append_event

        append_event(self.data, event)
        cultivation["updated_at"] = event["created_at"]
        await self.async_save()
        return event

    async def async_append_assistant_recommendation(
        self,
        *,
        note: str,
        provider_entity_id: str,
        context_summary: dict[str, Any],
        created_by: str = "",
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one generate-only assistant response to the active journal."""
        cultivation = self.active_cultivation
        if cultivation is None:
            raise ValueError("There is no active cultivation")
        clean_note = str(note or "").strip()[:4000]
        if not clean_note:
            raise ValueError("Assistant response is empty")
        if event_id:
            existing = next(
                (item for item in self.data.get("events", []) if item.get("id") == event_id),
                None,
            )
            if existing is not None:
                if existing.get("cultivation_id") != cultivation["id"]:
                    raise ValueError("Assistant event id belongs to another cultivation")
                return deepcopy(existing)
        timestamp = utc_now()
        event = make_event(
            event_type="ai_recommendation",
            cultivation_id=cultivation["id"],
            local_date=timestamp[:10],
            note=clean_note,
            data={
                "provider_entity_id": str(provider_entity_id)[:160],
                "context": context_summary,
                "read_only": True,
            },
            source="assistant",
            created_by=created_by,
            event_id=event_id,
            created_at=timestamp,
        )
        append_event(self.data, event)
        cultivation["updated_at"] = timestamp
        await self.async_save()
        return event

    def export_journal(self) -> dict[str, Any]:
        """Build a complete checksummed export suitable for off-device backup."""
        payload = {
            "export_version": 1,
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "generated_at": utc_now(),
            "cultivations": deepcopy(self.data.get("cultivations", empty_cultivations())),
            "events": deepcopy(self.data.get("events", [])),
            "current_system_profile": deepcopy(self.data.get("system_profile", {})),
            "plant_catalog": deepcopy(self.data.get("plant_catalog", {})),
        }
        return {**payload, "checksum": journal_checksum(payload)}

    async def async_update_profile(
        self, stage: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Update one profile and return it."""
        if stage not in self.data["profiles"]:
            raise ValueError(f"Unknown stage: {stage}")
        allowed = set(DEFAULT_PROFILES[stage]) - {"name"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if "nutrient_ids" in updates:
            if not isinstance(updates["nutrient_ids"], list):
                raise ValueError("nutrient_ids must be a list")
            valid_ids = {
                fluid.get("id")
                for fluid in self.data["hardware"].get("dosing_fluids", [])
                if fluid.get("id")
                and fluid.get("id") not in {"ph_up", "ph_down"}
                and fluid.get("category") not in {"ph_up", "ph_down"}
            }
            updates["nutrient_ids"] = list(dict.fromkeys(
                nutrient_id for nutrient_id in updates["nutrient_ids"]
                if isinstance(nutrient_id, str) and nutrient_id in valid_ids
            ))
        self.data["profiles"][stage].update(updates)
        await self.async_save()
        return self.data["profiles"][stage]

    async def async_update_system_profile(self, values: dict[str, Any]) -> dict[str, Any]:
        """Persist the user's cabin, water-system, and lighting profile."""
        self.data["system_profile"] = normalize_system_profile(values)
        await self.async_save()
        return deepcopy(self.data["system_profile"])

    async def async_update_assistant_settings(
        self, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist generate-only assistant preferences."""
        self.data["assistant_settings"] = normalize_assistant_settings(values)
        await self.async_save()
        return deepcopy(self.data["assistant_settings"])

    async def async_update_plant(
        self, plant_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or update one persistent plant-library record."""
        catalog = self.data.setdefault("plant_catalog", default_plant_catalog())
        existing = catalog.setdefault("records", {}).get(plant_id)
        fallback = existing or GENERIC_PLANT
        record = normalize_plant_record(
            values, plant_id=plant_id, fallback=fallback
        )
        if not record["name"]:
            raise ValueError("Plant name is required")
        catalog["records"][plant_id] = record
        order = catalog.setdefault("order", [])
        if plant_id not in order:
            order.append(plant_id)
        await self.async_save()
        return deepcopy(record)

    async def async_update_breeder(
        self, breeder_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or update one persistent breeder or seed-bank record."""
        catalog = self.data.setdefault("plant_catalog", default_plant_catalog())
        existing = catalog.setdefault("breeders", {}).get(breeder_id)
        record = normalize_breeder_record(
            values, breeder_id=breeder_id, fallback=existing
        )
        if not record["name"]:
            raise ValueError("Breeder or seed-bank name is required")
        catalog["breeders"][breeder_id] = record
        order = catalog.setdefault("breeder_order", [])
        if breeder_id not in order:
            order.append(breeder_id)
        await self.async_save()
        return deepcopy(record)

    def ensure_custom_plant(self, plant_id: str, name: str) -> dict[str, Any]:
        """Add a custom plant in memory; the cultivation save persists it atomically."""
        catalog = self.data.setdefault("plant_catalog", default_plant_catalog())
        records = catalog.setdefault("records", {})
        if plant_id in records:
            return deepcopy(records[plant_id])
        record = make_custom_plant_record(plant_id, name)
        records[plant_id] = record
        catalog.setdefault("order", []).append(plant_id)
        return deepcopy(record)

    async def async_update_hardware(self, values: dict[str, Any]) -> dict[str, Any]:
        """Persist validated native hardware preferences."""
        self.data["hardware"].update(values)
        await self.async_save()
        return self.data["hardware"]
