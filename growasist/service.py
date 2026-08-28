"""Home Assistant-independent cultivation and journal application service."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import math
import re
import secrets
from threading import RLock
import time
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
    utc_now,
)
from custom_components.hydroponic_system.nutrient_catalog import (
    program_matches_environment,
)
from custom_components.hydroponic_system.plant_catalog import (
    cultivation_plant_snapshot,
    make_custom_plant_record,
    normalize_plant_record,
    plant_plan,
)

from . import __version__
from .discovery import NetworkDiscovery
from .hardware_gateway import I2CHardwareGateway
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


def _network_identity_anchor(item: dict[str, Any]) -> str:
    mac = "".join(character for character in str(item.get("mac") or "").upper() if character.isalnum())
    return f"mac:{mac}" if len(mac) == 12 else f"id:{str(item.get('id') or '')}"


def _same_network_device(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_anchor = _network_identity_anchor(left)
    right_anchor = _network_identity_anchor(right)
    if left_anchor.startswith("mac:") and left_anchor == right_anchor:
        return True
    return bool(left.get("host") and left.get("host") == right.get("host"))


def _normalize_network_record(item: dict[str, Any]) -> None:
    """Backfill discovery v3 fields while retaining historical sightings."""
    vendor = str(item.get("vendor") or "Unknown")
    known_iot = vendor in {"Shelly", "Tuya", "TP-Link / Tapo", "Dreo", "Matter"}
    item.setdefault("manufacturer", "")
    item.setdefault("hostname", "")
    item.setdefault("ports", [item["port"]] if item.get("port") else [])
    item.setdefault("discovery_methods", [item.get("source") or item.get("protocol") or "legacy_scan"])
    item.setdefault("identity_confidence", 75 if item.get("supported") else 60 if known_iot else 45 if vendor != "Unknown" else 20)
    item.setdefault("category", "grow_iot" if known_iot else "other" if vendor != "Unknown" else "unknown")
    item.setdefault("evidence", ["Önceki keşif kaydı"])
    item.setdefault("adapter_available", False)
    item.setdefault("mac_local", False)


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


def _required_number(
    value: Any, *, field: str, low: float, high: float, integer: bool = False
) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} sayı olmalı") from error
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{field} {low:g}–{high:g} arasında olmalı")
    return int(round(number)) if integer else number


class GrowAsistService:
    """Serialize state mutations and expose product-level operations."""

    def __init__(self, store: GrowAsistStore) -> None:
        self.store = store
        self._mutation_lock = RLock()
        self._hardware_lock = RLock()
        self._calibration_runs: dict[str, dict[str, Any]] = {}

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
            "nutrient_catalog": deepcopy(state.get("nutrient_catalog", {})),
            "system_profile": deepcopy(state.get("system_profile", {})),
            "hardware": deepcopy(state.get("hardware", {})),
            "assistant_settings": deepcopy(state.get("assistant_settings", {})),
            "device_registry": deepcopy(state.get("device_registry", {})),
            "i2c_registry": deepcopy(state.get("i2c_registry", {})),
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
            catalog = state.get("nutrient_catalog", {})
            selected_program_id = _text(payload.get("nutrient_program_id"), 128)
            selected_program = catalog.get("programs", {}).get(selected_program_id)
            program_scope = _text(
                payload.get("nutrient_program_scope"), 16, "core"
            ).casefold()
            if program_scope not in {"core", "complete"}:
                raise ValueError("Besin programı kapsamı core veya complete olmalıdır")
            if selected_program_id and not isinstance(selected_program, dict):
                raise ValueError("Seçilen besin programı bulunamadı")
            if selected_program and not program_matches_environment(
                selected_program, growing_method, growing_medium
            ):
                raise ValueError("Seçilen besin programı yetiştirme ortamıyla uyumlu değil")

            selected_catalog_ids: list[str] = []
            if selected_program:
                selected_catalog_ids.extend(selected_program.get("core_product_ids", []))
                if program_scope == "complete":
                    selected_catalog_ids.extend(selected_program.get("optional_product_ids", []))
                selected_catalog_ids = list(dict.fromkeys(selected_catalog_ids))
                for catalog_id in selected_catalog_ids:
                    self._ensure_catalog_fluid(state, str(catalog_id))

            fluid_records = {
                str(item.get("id")): item
                for item in state.get("hardware", {}).get("dosing_fluids", [])
                if isinstance(item, dict)
                and item.get("id")
                and not item.get("required")
                and item.get("category") not in {"ph", "ph_up", "ph_down"}
            }
            requested_nutrients = payload.get("nutrient_ids", [])
            if not isinstance(requested_nutrients, list):
                raise ValueError("Besin ürünleri liste olarak gönderilmelidir")
            if selected_program:
                local_id_by_catalog = {
                    str(item.get("catalog_id")): local_id
                    for local_id, item in fluid_records.items()
                    if item.get("catalog_id")
                }
                nutrient_ids = [
                    local_id_by_catalog[catalog_id]
                    for catalog_id in selected_catalog_ids
                    if catalog_id in local_id_by_catalog
                ]
            else:
                nutrient_ids = list(dict.fromkeys(
                    str(item) for item in requested_nutrients if isinstance(item, str)
                ))
            unknown_nutrients = [item for item in nutrient_ids if item not in fluid_records]
            if unknown_nutrients:
                raise ValueError("Seçilen besin ürünü katalogda bulunamadı")
            nutrient_products = [deepcopy(fluid_records[item]) for item in nutrient_ids]
            catalog_program_name = (
                str(selected_program.get("name") or "") if selected_program else ""
            )
            nutrient_program = str(
                catalog_program_name
                or payload.get("nutrient_program")
                or " · ".join(str(item.get("name") or "") for item in nutrient_products)
            )[:160]
            stage_snapshot: dict[str, dict[str, list[str]]] = {}
            if selected_program:
                local_by_catalog = {
                    str(item.get("catalog_id")): str(item.get("id"))
                    for item in nutrient_products
                    if item.get("catalog_id") and item.get("id")
                }
                for stage, stage_products in selected_program.get("stages", {}).items():
                    stage_catalog_ids = list(stage_products.get("core_product_ids", []))
                    if program_scope == "complete":
                        stage_catalog_ids.extend(stage_products.get("optional_product_ids", []))
                    stage_catalog_ids = [
                        item for item in dict.fromkeys(stage_catalog_ids)
                        if item in selected_catalog_ids
                    ]
                    stage_snapshot[str(stage)] = {
                        "catalog_product_ids": stage_catalog_ids,
                        "nutrient_ids": [
                            local_by_catalog[item]
                            for item in stage_catalog_ids
                            if item in local_by_catalog
                        ],
                    }
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
                "nutrient_program": nutrient_program,
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
                    "name": nutrient_program,
                    "nutrient_ids": nutrient_ids,
                    "products": nutrient_products,
                    "program_id": selected_program_id,
                    "brand_id": (
                        str(selected_program.get("brand_id") or "")
                        if selected_program else ""
                    ),
                    "brand": (
                        str(selected_program.get("brand") or "")
                        if selected_program else ""
                    ),
                    "line": (
                        str(selected_program.get("line") or "")
                        if selected_program else ""
                    ),
                    "scope": program_scope if selected_program else "manual",
                    "catalog_product_ids": selected_catalog_ids,
                    "stages": stage_snapshot,
                    "catalog_version": str(catalog.get("catalog_version") or ""),
                    "source_url": (
                        str(selected_program.get("source_url") or "")
                        if selected_program else ""
                    ),
                    "dose_plan_included": False,
                    "source": "catalog_program" if selected_program else "standalone_grow_start",
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
            lighting = payload.get("lighting") if isinstance(payload, dict) else None
            device_id = str(lighting.get("device_id") or "") if isinstance(lighting, dict) else ""
            devices = state.get("device_registry", {}).get("devices", {})
            if device_id:
                device = devices.get(device_id) if isinstance(devices, dict) else None
                if not isinstance(device, dict) or device.get("role") not in {"light_dimmer", "light_power"}:
                    raise ValueError("Seçilen cihaz ışık kontrolü olarak tanımlı değil")
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
            current.pop("nutrient_ids", None)
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
            allowed_nutrients = {
                str(item.get("id"))
                for item in state.get("hardware", {}).get("dosing_fluids", [])
                if isinstance(item, dict)
                and item.get("id")
                and not item.get("required")
                and item.get("category") not in {"ph", "ph_up", "ph_down"}
            }
            profile = values.get("profile")
            stages = profile.get("stages") if isinstance(profile, dict) else None
            if isinstance(stages, dict):
                for target in stages.values():
                    if not isinstance(target, dict) or "nutrient_ids" not in target:
                        continue
                    requested = target.get("nutrient_ids")
                    if not isinstance(requested, list):
                        raise ValueError("Aşama besinleri liste olarak gönderilmelidir")
                    unknown = [
                        item for item in requested
                        if not isinstance(item, str) or item not in allowed_nutrients
                    ]
                    if unknown:
                        raise ValueError("Bitki aşamasında katalog dışı besin seçilemez")
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
            "form": _text(value.get("form"), 24),
            "input_type": _text(value.get("input_type"), 24),
            "description": _text(value.get("description"), 480),
            "source_url": _text(value.get("source_url"), 320),
            "verified_on": _text(value.get("verified_on"), 16),
            "official": bool(value.get("official", False)),
            "required": bool(required_id),
        }

    def add_catalog_nutrient(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Copy one official catalogue product into the user's fluid library."""
        catalog_id = _text(payload.get("catalog_id"), 96)
        if not catalog_id:
            raise ValueError("Katalog ürünü seçilmelidir")
        with self._mutation_lock:
            state = self.store.load_state()
            created, fluid = self._ensure_catalog_fluid(state, catalog_id)
            saved = self.store.save_state(state)
            stored = next(
                item for item in saved["hardware"]["dosing_fluids"]
                if item.get("id") == fluid["id"]
            )
            return {"created": created, "fluid": deepcopy(stored)}

    def _ensure_catalog_fluid(
        self, state: dict[str, Any], catalog_id: str
    ) -> tuple[bool, dict[str, Any]]:
        """Ensure one catalogue product exists locally without saving state."""
        product = state.get("nutrient_catalog", {}).get("products", {}).get(catalog_id)
        if not isinstance(product, dict):
            raise ValueError("Katalog ürünü bulunamadı")
        fluids = state.setdefault("hardware", {}).setdefault("dosing_fluids", [])
        existing = next(
            (
                item for item in fluids
                if isinstance(item, dict) and item.get("catalog_id") == catalog_id
            ),
            None,
        )
        if existing is not None:
            return False, existing
        fluid_id = f"nut_{hashlib.sha256(catalog_id.encode()).hexdigest()[:20]}"
        name = str(product.get("name") or catalog_id)
        lowered = name.casefold()
        ph_direction = ""
        if product.get("category") == "ph":
            ph_direction = "down" if any(word in lowered for word in ("down", "min")) else "up"
        raw = {
            key: deepcopy(product.get(key))
            for key in (
                "name", "brand", "category", "line", "part", "npk",
                "phase", "medium", "form", "input_type", "description",
                "source_url", "verified_on", "official",
            )
        }
        raw.update({
            "id": fluid_id,
            "catalog_id": catalog_id,
            "ph_direction": ph_direction,
            "required": False,
        })
        normalized = self._normalize_fluid(raw)
        fluids.append(normalized)
        return True, normalized

    def add_nutrient_program(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Copy a catalogue program's product set into the user's library atomically."""
        program_id = _text(payload.get("program_id"), 128)
        scope = _text(payload.get("scope"), 16, "core").casefold()
        if not program_id:
            raise ValueError("Besin programı seçilmelidir")
        if scope not in {"core", "complete"}:
            raise ValueError("Program kapsamı core veya complete olmalıdır")
        with self._mutation_lock:
            state = self.store.load_state()
            program = state.get("nutrient_catalog", {}).get("programs", {}).get(program_id)
            if not isinstance(program, dict):
                raise ValueError("Besin programı bulunamadı")
            catalog_ids = list(program.get("core_product_ids", []))
            if scope == "complete":
                catalog_ids.extend(program.get("optional_product_ids", []))
            added: list[dict[str, Any]] = []
            existing: list[dict[str, Any]] = []
            for catalog_id in dict.fromkeys(catalog_ids):
                created, fluid = self._ensure_catalog_fluid(state, str(catalog_id))
                (added if created else existing).append(deepcopy(fluid))
            saved = self.store.save_state(state)
            saved_by_id = {
                item["id"]: item for item in saved["hardware"]["dosing_fluids"]
            }
            return {
                "program_id": program_id,
                "scope": scope,
                "added": [deepcopy(saved_by_id[item["id"]]) for item in added],
                "existing": [deepcopy(saved_by_id[item["id"]]) for item in existing],
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

    def discover_i2c(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Discover the Raspberry Pi bus without changing any device output."""
        initial = self.store.load_state()
        hardware = initial.get("hardware", {})
        bus_number = int(hardware.get("i2c_bus", 1))
        result = I2CHardwareGateway(bus_number).scan(
            hardware.get("device_assignments", [])
        )
        with self._mutation_lock:
            state = self.store.load_state()
            registry = state.setdefault("i2c_registry", {})
            registry.update({
                "schema_version": 1,
                "health": deepcopy(result["health"]),
                "candidates": deepcopy(result["candidates"]),
                "last_scan": deepcopy(result["last_scan"]),
            })
            registry.setdefault("retired_assignments", [])
            state["engine_enabled"] = False
            saved = self.store.save_state(state)
            return deepcopy(saved["i2c_registry"])

    def enroll_i2c_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Approve one physically discovered I2C device; addresses are never typed."""
        with self._mutation_lock:
            state = self.store.load_state()
            registry = state.setdefault("i2c_registry", {})
            candidates = registry.setdefault("candidates", {})
            candidate_id = str(payload.get("candidate_id") or "")
            candidate = candidates.get(candidate_id)
            if not isinstance(candidate, dict):
                raise ValueError("Seçilen kablolu cihaz son taramada bulunamadı")
            if not candidate.get("online") or not candidate.get("supported"):
                raise ValueError("Cihaz çevrimiçi ve destekleniyor olmadan eklenemez")

            suggested = str(candidate.get("suggested_driver") or "")
            driver = str(payload.get("driver") or suggested)
            if candidate.get("driver_locked"):
                driver = suggested
            if driver not in _HARDWARE_DRIVERS:
                raise ValueError("Bu kart için geçerli bir sürücü seçin")
            if candidate.get("requires_driver_confirmation") and driver not in {
                "waveshare_motor_hat", "pca9685_generic",
            }:
                raise ValueError("PCA9685 kart tipini doğrulayın")

            hardware = deepcopy(state.get("hardware", {}))
            assignments = hardware.setdefault("device_assignments", [])
            address = int(candidate["address"])
            existing = next(
                (item for item in assignments if int(item.get("address", -1)) == address),
                None,
            )
            retired_match = next((
                item for item in reversed(registry.setdefault("retired_assignments", []))
                if int(item.get("address", -1)) == address
                and item.get("driver") == driver
            ), None)
            assignment = deepcopy(existing or retired_match or {})
            assignment.pop("removed_at", None)
            assignment.update({
                "address": address,
                "driver": driver,
                "name": _text(
                    payload.get("name"), 64,
                    str(candidate.get("model") or f"I²C 0x{address:02X}"),
                ),
            })
            if driver == "waveshare_motor_hat" and not assignment.get("channels"):
                assignment["channels"] = [
                    {"id": channel, "name": f"Motor {channel}", "fluid_id": "unassigned", "pump": {}, "calibration": None}
                    for channel in ("A", "B")
                ]
            if driver != "waveshare_motor_hat":
                assignment.pop("channels", None)
            if existing is None:
                assignments.append(assignment)
            else:
                assignments[assignments.index(existing)] = assignment

            fluid_ids = {
                str(item.get("id"))
                for item in hardware.get("dosing_fluids", [])
                if isinstance(item, dict) and item.get("id")
            }
            hardware["device_assignments"] = self._normalize_assignments(
                assignments, fluid_ids
            )
            state["hardware"] = hardware
            candidate.update({
                "configured": True,
                "enrolled": True,
                "driver": driver,
                "name": assignment["name"],
                "status": "online",
            })
            state["engine_enabled"] = False
            saved = self.store.save_state(state)
            return deepcopy(next(
                item for item in saved["hardware"]["device_assignments"]
                if item["address"] == address
            ))

    def remove_i2c_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Detach one configuration while keeping its audit snapshot and fluids."""
        with self._mutation_lock:
            state = self.store.load_state()
            hardware = deepcopy(state.get("hardware", {}))
            assignments = hardware.get("device_assignments", [])
            try:
                address = int(payload.get("address"))
            except (TypeError, ValueError) as error:
                raise ValueError("Kaldırılacak cihaz adresi geçersiz") from error
            removed = next(
                (item for item in assignments if int(item.get("address", -1)) == address),
                None,
            )
            if removed is None:
                raise ValueError("Kaldırılacak kablolu cihaz bulunamadı")
            hardware["device_assignments"] = [
                item for item in assignments if int(item.get("address", -1)) != address
            ]
            state["hardware"] = hardware
            registry = state.setdefault("i2c_registry", {})
            retired = registry.setdefault("retired_assignments", [])
            retired.append({**deepcopy(removed), "removed_at": utc_now()})
            registry["retired_assignments"] = retired[-64:]
            candidate_id = f"i2c_{int(hardware.get('i2c_bus', 1))}_{address:02x}"
            candidate = registry.setdefault("candidates", {}).get(candidate_id)
            if isinstance(candidate, dict):
                candidate.update({
                    "configured": False,
                    "enrolled": False,
                    "driver": "",
                    "name": str(candidate.get("model") or ""),
                    "status": "detected" if candidate.get("online") else "offline",
                })
            state["engine_enabled"] = False
            saved = self.store.save_state(state)
            return {
                "removed": deepcopy(removed),
                "hardware": deepcopy(saved["hardware"]),
            }

    @staticmethod
    def _pump_channel(
        state: dict[str, Any], address: int, channel_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        for assignment in state.get("hardware", {}).get("device_assignments", []):
            if int(assignment.get("address", -1)) != address:
                continue
            if assignment.get("driver") != "waveshare_motor_hat":
                raise ValueError("Seçilen cihaz bir Waveshare motor kartı değil")
            for channel in assignment.get("channels", []):
                if str(channel.get("id") or "").upper() == channel_id:
                    return assignment, channel
            break
        raise ValueError("Seçilen pompa kanalı yapılandırılmamış")

    @staticmethod
    def _confirmed(payload: dict[str, Any]) -> None:
        if payload.get("confirm") is not True:
            raise ValueError("Fiziksel güvenlik onayı gerekli")

    def test_pump(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run a manually confirmed 1-3 second pump test and always stop."""
        self._confirmed(payload)
        try:
            address = int(payload.get("address"))
        except (TypeError, ValueError) as error:
            raise ValueError("Motor kartı adresi geçersiz") from error
        channel_id = str(payload.get("channel") or "").upper()
        seconds = float(_required_number(
            payload.get("seconds"), field="Test süresi", low=1, high=3
        ))
        speed = int(_required_number(
            payload.get("speed"), field="Pompa hızı", low=20, high=100,
            integer=True,
        ))
        state = self.store.load_state()
        self._pump_channel(state, address, channel_id)
        bus_number = int(state.get("hardware", {}).get("i2c_bus", 1))
        with self._hardware_lock:
            I2CHardwareGateway(bus_number).run_pump(
                address, channel_id, seconds, speed
            )
        return {
            "address": address,
            "channel": channel_id,
            "seconds": seconds,
            "speed": speed,
            "stopped": True,
        }

    def start_pump_calibration(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run one measured calibration interval and issue a short-lived receipt."""
        self._confirmed(payload)
        try:
            address = int(payload.get("address"))
        except (TypeError, ValueError) as error:
            raise ValueError("Motor kartı adresi geçersiz") from error
        channel_id = str(payload.get("channel") or "").upper()
        seconds = float(_required_number(
            payload.get("seconds"), field="Kalibrasyon süresi", low=2, high=30
        ))
        speed = int(_required_number(
            payload.get("speed"), field="Pompa hızı", low=20, high=100,
            integer=True,
        ))
        state = self.store.load_state()
        self._pump_channel(state, address, channel_id)
        bus_number = int(state.get("hardware", {}).get("i2c_bus", 1))
        with self._hardware_lock:
            I2CHardwareGateway(bus_number).run_pump(
                address, channel_id, seconds, speed
            )
        token = secrets.token_urlsafe(24)
        with self._mutation_lock:
            self._calibration_runs[token] = {
                "address": address,
                "channel": channel_id,
                "seconds": seconds,
                "speed": speed,
                "expires_at": time.monotonic() + 600,
            }
        return {
            "token": token,
            "address": address,
            "channel": channel_id,
            "seconds": seconds,
            "speed": speed,
            "stopped": True,
        }

    def complete_pump_calibration(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist measured ml/s only for a just-completed physical run."""
        token = str(payload.get("token") or "")
        volume = float(_required_number(
            payload.get("volume_ml"), field="Ölçülen hacim", low=0.01, high=500
        ))
        with self._mutation_lock:
            run = self._calibration_runs.pop(token, None)
            if not run or float(run["expires_at"]) < time.monotonic():
                raise ValueError("Kalibrasyon ölçümü bulunamadı veya süresi doldu")
            state = self.store.load_state()
            _, channel = self._pump_channel(
                state, int(run["address"]), str(run["channel"])
            )
            calibration = {
                "seconds": float(run["seconds"]),
                "volume_ml": round(volume, 3),
                "speed": int(run["speed"]),
                "flow_ml_s": round(volume / float(run["seconds"]), 5),
                "calibrated_at": utc_now(),
            }
            channel["calibration"] = calibration
            channel["calibration_status"] = "measured"
            channel.setdefault("pump", {})["verified"] = True
            state["engine_enabled"] = False
            saved = self.store.save_state(state)
        _, saved_channel = self._pump_channel(
            saved, int(run["address"]), str(run["channel"])
        )
        return deepcopy(saved_channel)

    def discover_network(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Discover read-only LAN candidates and persist the scan inventory."""
        timeout = _bounded_number(payload.get("timeout"), 3, 1, 8)
        result = NetworkDiscovery(timeout=float(timeout)).scan()
        with self._mutation_lock:
            state = self.store.load_state()
            registry = state.setdefault("device_registry", {})
            registry["schema_version"] = 3
            devices = registry.setdefault("devices", {})
            candidates = registry.setdefault("candidates", {})
            overrides = registry.setdefault("identity_overrides", {})
            seen_ids = set()
            for candidate in result["candidates"]:
                candidate = deepcopy(candidate)
                override = overrides.get(_network_identity_anchor(candidate))
                if isinstance(override, dict):
                    for key in ("vendor", "model", "name", "category"):
                        if override.get(key):
                            candidate[key] = deepcopy(override[key])
                    candidate["identity_source"] = "user_confirmed"
                    candidate["identity_confidence"] = 100
                    candidate["supported"] = True
                    candidate["evidence"] = list(dict.fromkeys([
                        *(candidate.get("evidence") or []), "Kullanıcı tarafından doğrulandı"
                    ]))[:24]
                candidate_id = str(candidate["id"])
                matched_device_id = next(
                    (device_id for device_id, item in devices.items() if _same_network_device(item, candidate)),
                    None,
                )
                if matched_device_id is not None:
                    candidate_id = matched_device_id
                    candidate["id"] = candidate_id
                    seen_ids.add(candidate_id)
                    enrolled = devices[candidate_id]
                    for key in (
                        "host", "port", "ports", "mac", "model", "firmware",
                        "generation", "capabilities", "supported", "requires_auth",
                        "source", "last_seen", "hostname", "manufacturer", "protocol",
                        "discovery_methods", "identity_confidence", "identity_source",
                        "evidence", "category", "adapter_available", "mac_local",
                    ):
                        if key in candidate:
                            enrolled[key] = deepcopy(candidate[key])
                    enrolled["online"] = True
                    enrolled["connection_status"] = (
                        "credentials_required"
                        if enrolled.get("requires_auth")
                        else "adapter_pending"
                    )
                    for stale_id, stale in list(candidates.items()):
                        if _same_network_device(stale, candidate):
                            candidates.pop(stale_id, None)
                    continue
                matched_candidate_id = next(
                    (item_id for item_id, item in candidates.items() if _same_network_device(item, candidate)),
                    None,
                )
                if matched_candidate_id and matched_candidate_id != candidate_id:
                    candidates.pop(matched_candidate_id, None)
                seen_ids.add(candidate_id)
                candidates[candidate_id] = {**deepcopy(candidate), "online": True}
            for candidate_id, candidate in candidates.items():
                _normalize_network_record(candidate)
                if candidate_id not in seen_ids:
                    candidate["online"] = False
            for device_id, device in devices.items():
                _normalize_network_record(device)
                if device_id not in seen_ids:
                    device["online"] = False
            for candidate_id, candidate in list(candidates.items()):
                compact_mac = "".join(character for character in str(candidate.get("mac") or "") if character.isalnum()).upper()
                if compact_mac in {"000000000000", "FFFFFFFFFFFF"}:
                    candidates.pop(candidate_id, None)
            registry["last_scan"] = {
                key: deepcopy(value) for key, value in result.items() if key != "candidates"
            }
            saved = self.store.save_state(state)
            saved_registry = saved["device_registry"]
            return {
                "last_scan": deepcopy(saved_registry["last_scan"]),
                "candidates": deepcopy(saved_registry.get("candidates", {})),
                "devices": deepcopy(saved_registry.get("devices", {})),
            }

    def enroll_network_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Move one discovered candidate into the approved device inventory."""
        allowed_roles = {
            "unassigned", "environment_sensor", "co2_sensor", "light_dimmer",
            "light_power", "outlet_bank", "humidifier",
        }
        allowed_vendors = {"Shelly", "Tuya", "TP-Link / Tapo", "Dreo", "Matter", "Diğer"}
        with self._mutation_lock:
            state = self.store.load_state()
            registry = state.setdefault("device_registry", {})
            candidates = registry.setdefault("candidates", {})
            devices = registry.setdefault("devices", {})
            candidate_id = str(payload.get("candidate_id") or "")
            candidate = candidates.get(candidate_id) or devices.get(candidate_id)
            if not isinstance(candidate, dict):
                raise ValueError("Seçilen ağ cihazı adayı bulunamadı")
            manual_confirmation = bool(payload.get("confirm_identity"))
            requested_vendor = _text(payload.get("vendor"), 64, str(candidate.get("vendor") or "Unknown"))
            requested_model = _text(payload.get("model"), 96, str(candidate.get("model") or ""))
            if not candidate.get("supported") and not manual_confirmation:
                raise ValueError("Cihazın marka/model kimliğini doğrulayın")
            if manual_confirmation and requested_vendor not in allowed_vendors:
                raise ValueError("Seçilen cihaz üreticisi desteklenmiyor")
            role = str(payload.get("role") or candidate.get("suggested_role") or "unassigned")
            if role not in allowed_roles:
                raise ValueError("Bu cihaz rolü desteklenmiyor")
            device = deepcopy(candidate)
            if manual_confirmation:
                device.update({
                    "vendor": requested_vendor,
                    "model": requested_model,
                    "identity_source": "user_confirmed",
                    "identity_confidence": 100,
                    "supported": True,
                    "category": "grow_iot" if requested_vendor != "Diğer" else "other",
                })
                evidence = list(dict.fromkeys([
                    *(device.get("evidence") or []), "Kullanıcı tarafından doğrulandı"
                ]))[:24]
                device["evidence"] = evidence
            device.update({
                "name": _text(payload.get("name"), 96, str(candidate.get("name") or "Ağ cihazı")),
                "role": role,
                "status": "enrolled",
                "verified": False,
                "connection_status": (
                    "credentials_required"
                    if candidate.get("requires_auth")
                    else "adapter_pending"
                ),
                "enrolled_at": str(candidate.get("enrolled_at") or utc_now()),
            })
            devices[candidate_id] = device
            candidates.pop(candidate_id, None)
            registry["schema_version"] = 3
            registry.setdefault("assignments", {})[candidate_id] = {"role": role}
            if manual_confirmation:
                registry.setdefault("identity_overrides", {})[_network_identity_anchor(device)] = {
                    "vendor": device["vendor"],
                    "model": device["model"],
                    "name": device["name"],
                    "category": device["category"],
                    "confirmed_at": utc_now(),
                }
            saved = self.store.save_state(state)
            return deepcopy(saved["device_registry"]["devices"][candidate_id])

    def remove_network_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Remove an approved role but retain a visible discovery candidate."""
        with self._mutation_lock:
            state = self.store.load_state()
            registry = state.setdefault("device_registry", {})
            devices = registry.setdefault("devices", {})
            candidates = registry.setdefault("candidates", {})
            candidate_id = str(payload.get("candidate_id") or "")
            device = devices.pop(candidate_id, None)
            if not isinstance(device, dict):
                raise ValueError("Kaldırılacak ağ cihazı bulunamadı")
            candidate = deepcopy(device)
            for key in ("role", "enrolled_at", "verified", "connection_status"):
                candidate.pop(key, None)
            candidate["status"] = "candidate"
            candidates[candidate_id] = candidate
            registry.setdefault("assignments", {}).pop(candidate_id, None)
            retired = registry.setdefault("retired_devices", [])
            retired.append({**deepcopy(device), "removed_at": utc_now()})
            registry["retired_devices"] = retired[-64:]
            state["engine_enabled"] = False
            saved = self.store.save_state(state)
            return deepcopy(saved["device_registry"])
