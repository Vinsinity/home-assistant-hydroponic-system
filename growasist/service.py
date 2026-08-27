"""Home Assistant-independent cultivation and journal application service."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import math
import re
from threading import RLock
from typing import Any

from custom_components.hydroponic_system.const import (
    DEFAULT_DOSING_POLICY,
    DEFAULT_PROFILES,
    STAGE_ORDER,
)
from custom_components.hydroponic_system.grow_profile import normalize_system_profile
from custom_components.hydroponic_system.journal import (
    active_cultivation,
    append_event,
    cultivation_summaries,
    finish_cultivation,
    make_event,
    new_cultivation,
    normalize_user_event_values,
    select_stage,
    start_cultivation,
)
from custom_components.hydroponic_system.plant_catalog import (
    cultivation_plant_snapshot,
    make_custom_plant_record,
    normalize_plant_record,
    plant_plan,
)

from . import __version__
from .storage import GrowAsistStore


STAGE_LABELS = {
    "germination": "Çimlenme",
    "early_veg": "Erken gelişim",
    "veg": "Gelişim",
    "bloom": "Çiçeklenme",
    "darkness": "Karanlık",
    "harvest": "Hasat / Kurutma",
}

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_PROFILE_LIMITS = {
    "planned_days": (1, 365, True),
    "photoperiod": (0, 24, False),
    "light_intensity": (0, 100, False),
    "day_temperature": (0, 60, False),
    "night_temperature": (0, 60, False),
    "humidity": (0, 100, False),
    "vpd": (0, 5, False),
    "co2": (0, 5000, False),
    "ppm": (0, 5000, False),
    "water_temperature": (0, 40, False),
    "ph": (0, 14, False),
    "do_minimum": (0, 30, False),
}
_HARDWARE_DRIVERS = {
    "waveshare_motor_hat",
    "pca9685_generic",
    "atlas_do",
    "atlas_ph",
    "atlas_ec",
    "atlas_rtd",
}


def _bounded_number(value: Any, default: Any, low: float, high: float, integer: bool = False) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    number = max(low, min(high, number))
    return int(round(number)) if integer else round(number, 3)


def _text(value: Any, maximum: int, fallback: str = "") -> str:
    return str(value if value not in (None, "") else fallback).strip()[:maximum]


class GrowAsistService:
    """Serialize state mutations and expose product-level operations."""

    def __init__(self, store: GrowAsistStore) -> None:
        self.store = store
        self._mutation_lock = RLock()

    @staticmethod
    def _local_date(value: Any, *, field: str = "Tarih") -> str:
        """Accept a real local date, but never a future journal date."""
        text = str(value or date.today().isoformat())
        try:
            parsed = date.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"{field} YYYY-MM-DD olmalı") from error
        if parsed > date.today():
            raise ValueError(f"{field} gelecekte olamaz")
        return parsed.isoformat()

    def bootstrap(self) -> dict[str, Any]:
        """Return the authenticated standalone UI bootstrap payload."""
        state = self.store.load_state()
        active = active_cultivation(state)
        return {
            "service": "growasist-core",
            "version": __version__,
            "mode": "standalone",
            "engine_enabled": False,
            "active_stage": state.get("active_stage"),
            "active_cultivation": deepcopy(active),
            "cultivations": cultivation_summaries(state),
            "events": deepcopy(state.get("events", [])),
            "profiles": deepcopy(state.get("profiles", {})),
            "plant_catalog": deepcopy(state.get("plant_catalog", {})),
            "system_profile": deepcopy(state.get("system_profile", {})),
            "hardware": deepcopy(state.get("hardware", {})),
            "assistant_settings": deepcopy(state.get("assistant_settings", {})),
            "device_registry": deepcopy(state.get("device_registry", {})),
            "stage_labels": STAGE_LABELS,
            "storage": self.store.health(),
        }

    @staticmethod
    def _selected_plant(
        state: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        catalog = state.setdefault("plant_catalog", {})
        records = catalog.setdefault("records", {})
        profile_id = str(payload.get("plant_profile_id") or "").strip().lower()
        if profile_id:
            selected = records.get(profile_id)
            if selected is None:
                raise ValueError("Seçilen bitki profili bulunamadı")
            return selected

        species = str(payload.get("plant_species") or "").strip()
        if not species:
            raise ValueError("Bitki türü seçin veya yazın")
        selected = next(
            (
                item
                for item in records.values()
                if species.casefold()
                in {
                    str(item.get("name") or "").casefold(),
                    str(item.get("english_name") or "").casefold(),
                    str(item.get("botanical_name") or "").casefold(),
                    *(str(alias).casefold() for alias in item.get("aliases", [])),
                }
            ),
            None,
        )
        if selected is not None:
            return selected
        custom_id = "custom_" + hashlib.sha256(
            species.casefold().encode("utf-8")
        ).hexdigest()[:16]
        selected = make_custom_plant_record(custom_id, species)
        records[custom_id] = selected
        catalog.setdefault("order", []).append(custom_id)
        return selected

    @staticmethod
    def _genetics(
        state: dict[str, Any], selected_plant: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        catalog = state.get("plant_catalog", {})
        breeders = catalog.get("breeders", {})
        growth_types = {
            str(item.get("id")): item
            for item in selected_plant.get("growth_types", [])
            if isinstance(item, dict) and item.get("id")
        }
        cultivars = {
            str(item.get("id")): item
            for item in selected_plant.get("cultivars", [])
            if isinstance(item, dict) and item.get("id") and item.get("active", True)
        }
        cultivar_id = str(payload.get("cultivar_id") or "").strip().lower()
        cultivar = cultivars.get(cultivar_id) if cultivar_id else None
        if cultivar_id and cultivar is None:
            raise ValueError("Seçilen çeşit kütüphanede bulunamadı")

        growth_type_id = str(payload.get("growth_type") or "").strip().lower()
        breeder_id = str(payload.get("breeder_id") or "").strip().lower()
        custom_cultivar = str(payload.get("cultivar") or "").strip()[:96]
        if cultivar:
            growth_type_id = str(cultivar.get("growth_type") or growth_type_id)
            breeder_id = str(cultivar.get("breeder_id") or breeder_id)
        if selected_plant.get("category") == "cannabis" and not growth_type_id:
            raise ValueError("Cannabis için Photoperiod veya Autoflower seçin")

        growth_type = growth_types.get(growth_type_id) if growth_type_id else None
        if growth_type_id and growth_type is None:
            raise ValueError("Seçilen büyüme tipi bulunamadı")
        breeder = breeders.get(breeder_id) if breeder_id else None
        if breeder_id and breeder is None:
            raise ValueError("Seçilen üretici veya tohum bankası bulunamadı")

        cultivar_snapshot = deepcopy(
            cultivar
            or {
                "id": "",
                "name": custom_cultivar,
                "growth_type": growth_type_id,
                "breeder_id": breeder_id,
                "built_in": False,
            }
        )
        identity = {
            "cultivar_id": str(cultivar_snapshot.get("id") or ""),
            "cultivar": str(cultivar_snapshot.get("name") or custom_cultivar),
            "growth_type": growth_type_id,
            "breeder_id": breeder_id,
            "breeder_name": str(breeder.get("name") or "") if breeder else "",
            "source": str(payload.get("source") or "")[:160],
        }
        snapshot = {
            "growth_type": deepcopy(growth_type or {}),
            "breeder": deepcopy(breeder or {}),
            "cultivar": cultivar_snapshot,
            "source": identity["source"],
        }
        return identity, snapshot

    def start_cultivation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create one cultivation and its immutable lifecycle events."""
        with self._mutation_lock:
            state = self.store.load_state()
            if active_cultivation(state) is not None:
                raise ValueError("Önce aktif yetiştirmeyi tamamlayın")

            start_date = self._local_date(
                payload.get("start_date"), field="Başlangıç tarihi"
            )

            selected_plant = self._selected_plant(state, payload)
            genetics_identity, genetics_snapshot = self._genetics(
                state, selected_plant, payload
            )
            system = normalize_system_profile(state.get("system_profile"))
            growing_method = str(
                payload.get("growing_method")
                or system.get("system", {}).get("growing_method")
                or "RDWC"
            )[:64]
            growing_medium = str(
                payload.get("growing_medium")
                or system.get("system", {}).get("growing_medium")
                or ""
            )[:96]
            identity = {
                "plant_profile_id": selected_plant["id"],
                "plant_species": selected_plant["name"],
                "botanical_name": selected_plant.get("botanical_name", ""),
                "plant_count": payload.get("plant_count", 1),
                "growing_method": growing_method,
                "growing_medium": growing_medium,
                "reservoir_volume_l": payload.get(
                    "reservoir_volume_l",
                    system.get("system", {}).get("reservoir_volume_l", 0),
                ),
                "system_volume_l": payload.get(
                    "system_volume_l",
                    system.get("system", {}).get("system_volume_l", 0),
                ),
                "photoperiod": "profile",
                "nutrient_program": str(payload.get("nutrient_program") or "")[:160],
                "notes": str(payload.get("notes") or "")[:4000],
                **genetics_identity,
            }
            plan = plant_plan(selected_plant)
            cultivation = new_cultivation(
                name=str(payload.get("name") or "")[:80],
                start_date=start_date,
                identity=identity,
                plan=plan,
                system_snapshot=system,
                plant_profile_snapshot=cultivation_plant_snapshot(
                    selected_plant,
                    genetics_snapshot.get("cultivar"),
                    catalog_version=str(
                        state.get("plant_catalog", {}).get("catalog_version") or ""
                    ),
                ),
                genetics_snapshot=genetics_snapshot,
                nutrient_program_snapshot={
                    "name": identity["nutrient_program"],
                    "nutrient_ids": [],
                    "products": [],
                    "source": "standalone_grow_start",
                },
                initial_stage=str(payload.get("initial_stage") or "") or None,
                cultivation_id=payload.get("cultivation_id"),
            )
            start_cultivation(state, cultivation, created_by="standalone_ui")
            saved = self.store.save_state(state)
            return deepcopy(saved["cultivations"]["records"][cultivation["id"]])

    def append_journal_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Append one user event; no update or delete operation exists."""
        with self._mutation_lock:
            state = self.store.load_state()
            cultivation = active_cultivation(state)
            if cultivation is None:
                raise ValueError("Günlük kaydı için aktif yetiştirme gerekli")
            event_type = str(payload.get("type") or "user_note")
            note = str(payload.get("note") or "").strip()
            if event_type != "photo" and not note:
                raise ValueError("Günlük notu boş olamaz")
            event = make_event(
                event_type=event_type,
                cultivation_id=cultivation["id"],
                local_date=self._local_date(payload.get("local_date")),
                note=note,
                data=normalize_user_event_values(event_type, payload.get("values")),
                source="user",
                created_by="standalone_ui",
                event_id=payload.get("event_id"),
            )
            append_event(state, event)
            cultivation["updated_at"] = event["created_at"]
            saved = self.store.save_state(state)
            return deepcopy(next(item for item in saved["events"] if item["id"] == event["id"]))

    def select_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Append a valid stage transition to the active cultivation."""
        with self._mutation_lock:
            state = self.store.load_state()
            cultivation = active_cultivation(state)
            if cultivation is None:
                raise ValueError("Aşama değiştirmek için aktif yetiştirme gerekli")
            stage = str(payload.get("stage") or "")
            allowed = {str(item.get("stage")) for item in cultivation.get("plan", [])}
            if stage not in allowed:
                raise ValueError("Bu aşama yetiştirme planında etkin değil")
            select_stage(
                state,
                stage,
                local_date=self._local_date(payload.get("local_date")),
                created_by="standalone_ui",
            )
            saved = self.store.save_state(state)
            return {
                "active_stage": saved.get("active_stage"),
                "cultivation": deepcopy(active_cultivation(saved)),
            }

    def finish_cultivation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Archive the active cultivation without deleting its events."""
        with self._mutation_lock:
            state = self.store.load_state()
            result = finish_cultivation(
                state,
                local_date=self._local_date(payload.get("local_date")),
                created_by="standalone_ui",
            )
            self.store.save_state(state)
            return deepcopy(result)

    def update_system_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist the reusable grow-area, medium, and fixture context."""
        with self._mutation_lock:
            state = self.store.load_state()
            state["system_profile"] = normalize_system_profile(payload)
            saved = self.store.save_state(state)
            return deepcopy(saved["system_profile"])

    def update_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist one editable example stage profile without enabling control."""
        with self._mutation_lock:
            state = self.store.load_state()
            stage = str(payload.get("stage") or "")
            if stage not in STAGE_ORDER:
                raise ValueError("Bilinmeyen yetiştirme aşaması")
            values = payload.get("values")
            if not isinstance(values, dict):
                raise ValueError("Profil değerleri bir nesne olmalı")
            current = deepcopy(state.get("profiles", {}).get(stage, DEFAULT_PROFILES[stage]))
            for key, (low, high, integer) in _PROFILE_LIMITS.items():
                if key in values:
                    current[key] = _bounded_number(
                        values[key], DEFAULT_PROFILES[stage][key], low, high, integer
                    )
            fluids = state.get("hardware", {}).get("dosing_fluids", [])
            allowed_fluids = {
                str(item.get("id"))
                for item in fluids
                if isinstance(item, dict)
                and item.get("id")
                and item.get("id") not in {"ph_up", "ph_down"}
            }
            if "nutrient_ids" in values:
                requested = values.get("nutrient_ids")
                if not isinstance(requested, list):
                    raise ValueError("Besin eşlemesi bir liste olmalı")
                current["nutrient_ids"] = list(
                    dict.fromkeys(
                        item for item in requested
                        if isinstance(item, str) and item in allowed_fluids
                    )
                )
            current["name"] = DEFAULT_PROFILES[stage]["name"]
            state.setdefault("profiles", {})[stage] = current
            saved = self.store.save_state(state)
            return deepcopy(saved["profiles"][stage])

    def update_plant(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create or update one plant library record and its example targets."""
        with self._mutation_lock:
            state = self.store.load_state()
            catalog = state.setdefault("plant_catalog", {})
            records = catalog.setdefault("records", {})
            plant_id = str(payload.get("plant_id") or "").strip().lower()
            if not _ID_PATTERN.fullmatch(plant_id):
                raise ValueError("Bitki kimliği küçük harf, rakam, _ veya - kullanmalı")
            values = payload.get("values")
            if not isinstance(values, dict):
                raise ValueError("Bitki kaydı bir nesne olmalı")
            fallback = records.get(plant_id)
            if fallback is None:
                name = _text(values.get("name"), 96)
                if not name:
                    raise ValueError("Bitki adı gerekli")
                fallback = make_custom_plant_record(plant_id, name)
            normalized = normalize_plant_record(
                values, plant_id=plant_id, fallback=fallback
            )
            records[plant_id] = normalized
            order = catalog.setdefault("order", [])
            if plant_id not in order:
                order.append(plant_id)
            saved = self.store.save_state(state)
            return deepcopy(saved["plant_catalog"]["records"][plant_id])

    @staticmethod
    def _normalize_fluid(value: Any, *, required_id: str | None = None) -> dict[str, Any]:
        value = value if isinstance(value, dict) else {}
        fluid_id = required_id or _text(value.get("id"), 64).lower()
        if not _ID_PATTERN.fullmatch(fluid_id):
            raise ValueError(f"Geçersiz sıvı kimliği: {fluid_id}")
        default_name = "pH+" if fluid_id == "ph_up" else "pH−" if fluid_id == "ph_down" else fluid_id
        return {
            "id": fluid_id,
            "name": _text(value.get("name"), 64, default_name),
            "brand": _text(value.get("brand"), 64, "Belirtilmedi"),
            "category": "ph" if required_id else _text(value.get("category"), 32, "other"),
            "catalog_id": _text(value.get("catalog_id"), 96),
            "line": _text(value.get("line"), 64),
            "part": _text(value.get("part"), 32),
            "npk": _text(value.get("npk"), 32),
            "phase": _text(value.get("phase"), 32),
            "medium": _text(value.get("medium"), 32),
            "ph_direction": _text(value.get("ph_direction"), 8),
            "required": bool(required_id),
        }

    @staticmethod
    def _normalize_calibration(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        seconds = _bounded_number(value.get("seconds"), 0, 0, 30)
        volume = _bounded_number(value.get("volume_ml"), 0, 0, 500)
        speed = _bounded_number(value.get("speed"), 100, 20, 100, True)
        if seconds < 1 or volume <= 0:
            return None
        return {
            "seconds": round(float(seconds), 2),
            "volume_ml": round(float(volume), 3),
            "speed": speed,
            "flow_ml_s": round(float(volume) / float(seconds), 5),
            "calibrated_at": _text(value.get("calibrated_at"), 40),
        }

    @classmethod
    def _normalize_assignments(cls, value: Any, fluid_ids: set[str]) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("Donanım atamaları bir liste olmalı")
        result = []
        addresses: set[int] = set()
        for raw in value[:32]:
            if not isinstance(raw, dict):
                continue
            try:
                address = int(str(raw.get("address")), 0)
            except (TypeError, ValueError) as error:
                raise ValueError("I²C adresi sayı veya 0x biçiminde olmalı") from error
            driver = str(raw.get("driver") or "")
            if not 0x08 <= address <= 0x77 or driver not in _HARDWARE_DRIVERS:
                raise ValueError("Geçersiz I²C adresi veya sürücüsü")
            if address in addresses:
                raise ValueError(f"0x{address:02X} adresi birden fazla kez kullanılmış")
            addresses.add(address)
            item = {
                "address": address,
                "driver": driver,
                "name": _text(raw.get("name"), 64, f"I²C 0x{address:02X}"),
            }
            if driver == "waveshare_motor_hat":
                incoming = {
                    str(channel.get("id") or "").upper(): channel
                    for channel in raw.get("channels", [])
                    if isinstance(channel, dict)
                }
                channels = []
                for channel_id in ("A", "B"):
                    channel = incoming.get(channel_id, {})
                    fluid_id = str(channel.get("fluid_id") or "unassigned")
                    if fluid_id != "unassigned" and fluid_id not in fluid_ids:
                        raise ValueError(f"Bilinmeyen dozaj sıvısı: {fluid_id}")
                    calibration = cls._normalize_calibration(channel.get("calibration"))
                    pump = channel.get("pump") if isinstance(channel.get("pump"), dict) else {}
                    channels.append({
                        "id": channel_id,
                        "name": _text(channel.get("name"), 64, f"Motor {channel_id}"),
                        "fluid_id": fluid_id,
                        "pump": {
                            "catalog_id": _text(pump.get("catalog_id"), 64, "nkp_dcl_s10y"),
                            "brand": _text(pump.get("brand"), 64, "NKP"),
                            "model": _text(pump.get("model"), 64, "NKP-DCL-S10Y"),
                            "pump_type": _text(pump.get("pump_type"), 32, "peristaltic_dc"),
                            "voltage": _bounded_number(pump.get("voltage"), 12, 0, 48),
                            "power_w": _bounded_number(pump.get("power_w"), 5, 0, 100),
                            "current_a": _bounded_number(pump.get("current_a"), 0.417, 0, 20),
                            "flow_min_ml_min": _bounded_number(pump.get("flow_min_ml_min"), 0, 0, 10000),
                            "flow_max_ml_min": _bounded_number(pump.get("flow_max_ml_min"), 0, 0, 10000),
                            "pwm": bool(pump.get("pwm", True)),
                            "reversible": bool(pump.get("reversible", True)),
                            "verified": bool(pump.get("verified", False)),
                        },
                        "calibration": calibration,
                        "calibration_status": "measured" if calibration else "unverified",
                    })
                item["channels"] = channels
            result.append(item)
        return result

    @staticmethod
    def _normalize_dosing_policy(value: Any) -> dict[str, Any]:
        value = value if isinstance(value, dict) else {}
        limits = {
            "nutrient_interval_minutes": (30, 1440, True),
            "mixing_wait_minutes": (5, 180, True),
            "remeasure_wait_minutes": (1, 60, True),
            "ph_interval_minutes": (10, 360, True),
            "ph_deadband": (0.02, 1, False),
            "max_nutrient_dose_ml": (0.1, 500, False),
            "max_ph_dose_ml": (0.1, 50, False),
        }
        result = {}
        for key, (low, high, integer) in limits.items():
            result[key] = _bounded_number(
                value.get(key), DEFAULT_DOSING_POLICY[key], low, high, integer
            )
        result["ph_single_direction"] = True
        result["sequence"] = "nutrients_mix_remeasure_ph"
        return result

    def update_hardware(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist hardware definitions, fluid mappings and safety limits only."""
        with self._mutation_lock:
            state = self.store.load_state()
            hardware = deepcopy(state.get("hardware", {}))
            for key in ("i2c_bus", "poll_interval", "device_assignments", "dosing_fluids", "dosing_policy"):
                if key in payload:
                    hardware[key] = deepcopy(payload[key])

            raw_fluids = hardware.get("dosing_fluids", [])
            if not isinstance(raw_fluids, list):
                raise ValueError("Besin ve sıvı kataloğu bir liste olmalı")
            indexed = {
                str(item.get("id")): item
                for item in raw_fluids
                if isinstance(item, dict) and item.get("id")
            }
            fluids = [
                self._normalize_fluid(indexed.get("ph_up"), required_id="ph_up"),
                self._normalize_fluid(indexed.get("ph_down"), required_id="ph_down"),
            ]
            seen = {"ph_up", "ph_down"}
            for raw in raw_fluids:
                if not isinstance(raw, dict):
                    continue
                fluid_id = str(raw.get("id") or "").lower()
                if not fluid_id or fluid_id in seen:
                    continue
                fluid = self._normalize_fluid(raw)
                seen.add(fluid["id"])
                fluids.append(fluid)

            hardware = {
                "i2c_bus": _bounded_number(hardware.get("i2c_bus"), 1, 0, 255, True),
                "poll_interval": _bounded_number(hardware.get("poll_interval"), 30, 10, 300, True),
                "dosing_policy": self._normalize_dosing_policy(hardware.get("dosing_policy")),
                "dosing_fluids": fluids,
                "device_assignments": self._normalize_assignments(
                    hardware.get("device_assignments", []), seen
                ),
            }
            state["hardware"] = hardware
            state["engine_enabled"] = False
            saved = self.store.save_state(state)
            return deepcopy(saved["hardware"])
