"""Home Assistant-independent cultivation and journal application service."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
from threading import RLock
from typing import Any

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
            "plant_catalog": deepcopy(state.get("plant_catalog", {})),
            "system_profile": deepcopy(state.get("system_profile", {})),
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
