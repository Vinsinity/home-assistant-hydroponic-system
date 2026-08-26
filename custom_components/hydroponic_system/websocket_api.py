"""WebSocket API used by the Hydroponic System panel."""

from __future__ import annotations

from datetime import date
import json

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import CONTROL_KEYS, DEFAULT_CULTIVATION_PLAN, DEFAULT_DOSING_POLICY, DOMAIN, SENSOR_KEYS, STAGE_ORDER
from .entity_map import resolve_entities
from .grow_profile import (
    assistant_context_summary,
    build_assistant_prompt,
    normalize_assistant_settings,
    normalize_sensor_summaries,
    normalize_system_profile,
    system_profile_completeness,
)
from .journal import (
    USER_EVENT_TYPES,
    empty_cultivation_view,
    events_for_cultivation,
    new_cultivation,
)
from .readiness import cultivation_readiness


def _live_atlas_drivers(atlas) -> set[str]:
    """Return drivers for Atlas circuits that are currently discovered."""
    if atlas is None:
        return set()
    return {
        f"atlas_{str(device.device_type).lower()}"
        for device in atlas.devices
        if device.key in (atlas.data or {})
    }


@websocket_api.websocket_command({vol.Required("type"): "hydroponic_system/config/get"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_get_config(hass, connection, msg) -> None:
    """Return the complete compact profile document."""
    store = hass.data[DOMAIN]["store"]
    configured = hass.data[DOMAIN].get("configured_entities", {})
    entities = resolve_entities(hass, configured)
    hass.data[DOMAIN]["entities"] = entities
    atlas = hass.data[DOMAIN].get("atlas_i2c")
    readiness = cultivation_readiness(
        entities, store.data.get("hardware", {}), _live_atlas_drivers(atlas)
    )
    cultivation = store.active_cultivation or empty_cultivation_view()
    cultivation_events = events_for_cultivation(
        store.data, cultivation.get("id") if cultivation.get("active") else None
    )
    providers = [
        {
            "id": state.entity_id,
            "name": state.name,
            "available": state.state not in {"unavailable", "unknown"},
        }
        for state in hass.states.async_all()
        if state.domain == "ai_task"
    ]
    connection.send_result(
        msg["id"],
        {
            **store.data,
            "cultivation": cultivation,
            "calendar": store.active_calendar(),
            "cultivation_history": store.cultivation_history(),
            "journal_integrity": store.journal_diagnostic,
            "hardware_config": store.data.get("hardware", {}),
            "entities": entities,
            "configured_entities": configured,
            "cultivation_readiness": readiness,
            "system_profile_status": system_profile_completeness(
                store.data.get("system_profile")
            ),
            "assistant": {
                "providers": providers,
                "generate_service_available": hass.services.has_service(
                    "ai_task", "generate_data"
                ),
                "context": assistant_context_summary(
                    cultivation=cultivation,
                    system_profile=(
                        cultivation.get("system_snapshot")
                        or store.data.get("system_profile")
                    ),
                    sensor_summaries=[],
                    recent_events=cultivation_events,
                ),
            },
            "hardware": {
                "atlas_i2c": atlas.diagnostic if atlas is not None else {
                    "available": False,
                    "error": "Native I2C coordinator is not initialized",
                }
            },
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/entities/save",
        vol.Required("values"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_entities(hass, connection, msg) -> None:
    """Persist panel-managed sensor and equipment mappings."""
    allowed = set(SENSOR_KEYS) | set(CONTROL_KEYS)
    clean = {}
    for key, value in msg["values"].items():
        if key not in allowed:
            continue
        if isinstance(value, str):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            clean[key] = value

    entry = hass.data[DOMAIN]["entry"]
    current = {**entry.data, **entry.options}
    current.update(clean)
    hass.config_entries.async_update_entry(entry, options=current)
    connection.send_result(msg["id"], clean)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/profile/save",
        vol.Required("stage"): vol.In(STAGE_ORDER),
        vol.Required("values"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_profile(hass, connection, msg) -> None:
    """Save one stage profile."""
    store = hass.data[DOMAIN]["store"]
    try:
        profile = await store.async_update_profile(msg["stage"], msg["values"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_stage", str(err))
        return
    cultivation = store.active_cultivation
    if cultivation is not None:
        for block in cultivation.get("plan", []):
            if block.get("stage") == msg["stage"]:
                block["planned_days"] = max(1, min(365, int(profile["planned_days"])))
                await store.async_save()
                break
    connection.send_result(msg["id"], profile)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/system_profile/save",
        vol.Required("values"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_system_profile(hass, connection, msg) -> None:
    """Persist the simple cabin, water-system, and lighting profile."""
    store = hass.data[DOMAIN]["store"]
    profile = await store.async_update_system_profile(msg["values"])
    connection.send_result(
        msg["id"],
        {"profile": profile, "status": system_profile_completeness(profile)},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/assistant/settings/save",
        vol.Required("values"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_assistant_settings(hass, connection, msg) -> None:
    """Persist generate-only assistant preferences."""
    settings = normalize_assistant_settings(msg["values"])
    provider = settings["provider_entity_id"]
    if provider and hass.states.get(provider) is None:
        connection.send_error(
            msg["id"], "provider_not_found", "Selected AI Task provider was not found"
        )
        return
    saved = await hass.data[DOMAIN]["store"].async_update_assistant_settings(settings)
    connection.send_result(msg["id"], saved)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/assistant/generate",
        vol.Optional("sensor_summaries", default=[]): list,
        vol.Optional("event_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_generate_assistant_report(hass, connection, msg) -> None:
    """Generate and journal one read-only report through Home Assistant AI Task."""
    store = hass.data[DOMAIN]["store"]
    cultivation = store.active_cultivation
    if cultivation is None:
        connection.send_error(
            msg["id"], "no_active_cultivation", "Start a cultivation before using Assistant"
        )
        return
    settings = normalize_assistant_settings(store.data.get("assistant_settings"))
    provider = settings["provider_entity_id"]
    if not provider:
        connection.send_error(
            msg["id"], "provider_required", "Select a Home Assistant AI Task provider"
        )
        return
    if hass.states.get(provider) is None:
        connection.send_error(msg["id"], "provider_not_found", "AI Task provider is unavailable")
        return
    if not hass.services.has_service("ai_task", "generate_data"):
        connection.send_error(msg["id"], "service_unavailable", "AI Task service is unavailable")
        return

    sensor_summaries = normalize_sensor_summaries(msg.get("sensor_summaries"))
    cultivation_events = events_for_cultivation(store.data, cultivation["id"])
    stage = store.data.get("active_stage")
    prompt = build_assistant_prompt(
        cultivation=cultivation,
        active_stage=stage,
        active_profile=store.data.get("profiles", {}).get(stage) if stage else None,
        system_profile=store.data.get("system_profile"),
        sensor_summaries=sensor_summaries,
        recent_events=cultivation_events,
        settings=settings,
    )
    service_data = {
        "entity_id": provider,
        "task_name": "Hydroponic System günlük yetiştirme özeti",
        "instructions": prompt,
    }
    if settings["allow_photos"]:
        configured_cameras = hass.data[DOMAIN].get("entities", {}).get("cameras", [])
        if isinstance(configured_cameras, str):
            configured_cameras = [configured_cameras]
        camera_ids = [
            entity_id
            for entity_id in configured_cameras
            if isinstance(entity_id, str) and entity_id.startswith("camera.")
        ][:3]
        if camera_ids:
            service_data["attachments"] = [
                {
                    "media_content_id": f"media-source://camera/{entity_id}",
                    "media_content_type": "image/jpeg",
                }
                for entity_id in camera_ids
            ]
    try:
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            service_data,
            blocking=True,
            context=connection.context(msg),
            return_response=True,
        )
        generated = response.get("data") if isinstance(response, dict) else response
        if isinstance(generated, dict):
            generated = json.dumps(generated, ensure_ascii=False)
        report = str(generated or "").strip()
        context_summary = assistant_context_summary(
            cultivation=cultivation,
            system_profile=cultivation.get("system_snapshot") or store.data.get("system_profile"),
            sensor_summaries=sensor_summaries,
            recent_events=cultivation_events,
        )
        event = await store.async_append_assistant_recommendation(
            note=report,
            provider_entity_id=provider,
            context_summary=context_summary,
            created_by=str(getattr(connection.user, "id", "")),
            event_id=msg.get("event_id"),
        )
        if settings["notifications"]:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Hydroponic System · Grow Assistant",
                    "message": report,
                    "notification_id": "hydroponic_system_grow_assistant",
                },
                blocking=True,
                context=connection.context(msg),
            )
    except (HomeAssistantError, TypeError, ValueError) as err:
        connection.send_error(msg["id"], "assistant_failed", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "report": report,
            "event": event,
            "read_only": True,
            "provider_entity_id": provider,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/stage/select",
        vol.Required("stage"): vol.In(STAGE_ORDER),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_select_stage(hass, connection, msg) -> None:
    """Select a stage for an active cultivation."""
    store = hass.data[DOMAIN]["store"]
    if store.active_cultivation is None:
        connection.send_error(
            msg["id"], "no_active_cultivation",
            "A stage cannot be activated before cultivation starts",
        )
        return
    try:
        await store.async_select_stage(
            msg["stage"],
            local_date=dt_util.now().date().isoformat(),
            created_by=str(getattr(connection.user, "id", "")),
        )
    except ValueError as err:
        connection.send_error(msg["id"], "stage_transition_failed", str(err))
        return
    connection.send_result(msg["id"], {"active_stage": msg["stage"]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/cultivation/start",
        vol.Optional("name", default=""): str,
        vol.Optional("start_date", default=""): str,
        vol.Optional("identity", default={}): dict,
        vol.Optional("cultivation_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_start_cultivation(hass, connection, msg) -> None:
    """Start a dated cultivation journal without forcing stage transitions."""
    store = hass.data[DOMAIN]["store"]
    if store.active_cultivation is not None:
        if msg.get("cultivation_id") == store.active_cultivation.get("id"):
            await store.async_save()
            connection.send_result(msg["id"], store.active_cultivation)
            return
        connection.send_error(msg["id"], "already_active", "A cultivation is already active")
        return
    today = dt_util.now().date()
    start_date = msg.get("start_date") or today.isoformat()
    try:
        parsed_start = date.fromisoformat(start_date)
    except ValueError:
        connection.send_error(msg["id"], "invalid_date", "Start date must be YYYY-MM-DD")
        return
    if parsed_start > today:
        connection.send_error(msg["id"], "invalid_date", "Start date cannot be in the future")
        return
    plan = []
    defaults_by_stage = {item["stage"]: item for item in DEFAULT_CULTIVATION_PLAN}
    for stage in STAGE_ORDER:
        defaults = defaults_by_stage[stage]
        profile = store.data["profiles"][stage]
        plan.append({
            **defaults,
            "planned_days": max(1, min(365, int(profile["planned_days"]))),
        })
    try:
        cultivation = new_cultivation(
            name=msg.get("name", ""),
            start_date=start_date,
            identity=msg.get("identity", {}),
            plan=plan,
            system_snapshot=normalize_system_profile(
                store.data.get("system_profile")
            ),
            cultivation_id=msg.get("cultivation_id"),
        )
        if not cultivation["identity"]["plant_species"]:
            raise ValueError("Plant species is required")
        cultivation = await store.async_start_cultivation(
            cultivation, created_by=str(getattr(connection.user, "id", ""))
        )
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_cultivation", str(err))
        return
    connection.send_result(msg["id"], cultivation)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/cultivation/finish",
        vol.Optional("cultivation_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_finish_cultivation(hass, connection, msg) -> None:
    """Finish the active cultivation while retaining its journal."""
    store = hass.data[DOMAIN]["store"]
    if store.active_cultivation is None and msg.get("cultivation_id"):
        archived = store.data.get("cultivations", {}).get("records", {}).get(
            msg["cultivation_id"]
        )
        if archived is not None and not archived.get("active"):
            await store.async_save()
            connection.send_result(msg["id"], archived)
            return
    try:
        cultivation = await store.async_finish_cultivation(
            local_date=dt_util.now().date().isoformat(),
            created_by=str(getattr(connection.user, "id", ""))
        )
    except ValueError as err:
        connection.send_error(msg["id"], "no_active_cultivation", str(err))
        return
    connection.send_result(msg["id"], cultivation)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/cultivation/event/add",
        vol.Required("event_type"): vol.In(USER_EVENT_TYPES),
        vol.Required("local_date"): str,
        vol.Optional("note", default=""): str,
        vol.Optional("values", default={}): dict,
        vol.Optional("event_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_add_cultivation_event(hass, connection, msg) -> None:
    """Append one immutable daily event to the active cultivation."""
    store = hass.data[DOMAIN]["store"]
    cultivation = store.active_cultivation
    if cultivation is None:
        connection.send_error(msg["id"], "no_active_cultivation", "There is no active cultivation")
        return
    try:
        local_date = date.fromisoformat(msg["local_date"])
        start_date = date.fromisoformat(cultivation["start_date"])
    except (TypeError, ValueError):
        connection.send_error(msg["id"], "invalid_date", "Event date must be YYYY-MM-DD")
        return
    if not start_date <= local_date <= dt_util.now().date():
        connection.send_error(
            msg["id"],
            "invalid_date",
            "Event date must be between cultivation start and today",
        )
        return
    try:
        event = await store.async_append_event(
            event_type=msg["event_type"],
            local_date=local_date.isoformat(),
            note=msg.get("note", ""),
            values=msg.get("values", {}),
            created_by=str(getattr(connection.user, "id", "")),
            event_id=msg.get("event_id"),
        )
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_event", str(err))
        return
    connection.send_result(msg["id"], event)


@websocket_api.websocket_command(
    {vol.Required("type"): "hydroponic_system/cultivation/export"}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_export_cultivations(hass, connection, msg) -> None:
    """Return every cultivation and event in a checksummed JSON document."""
    store = hass.data[DOMAIN]["store"]
    connection.send_result(msg["id"], store.export_journal())


def _address(value) -> int:
    """Normalize and validate a user supplied 7-bit I2C address."""
    address = int(value, 0) if isinstance(value, str) else int(value)
    if not 0x08 <= address <= 0x77:
        raise ValueError("I2C address must be between 0x08 and 0x77")
    return address


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/hardware/save",
        vol.Required("poll_interval"): vol.All(int, vol.Range(min=10, max=300)),
        vol.Optional("device_assignments", default=[]): list,
        vol.Optional("dosing_fluids", default=[]): list,
        vol.Optional("dosing_policy", default={}): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_hardware(hass, connection, msg) -> None:
    """Save native I2C preferences and apply them without a reload."""
    try:
        assignments = []
        assigned = set()
        allowed_drivers = {
            "waveshare_motor_hat", "pca9685_generic",
            "atlas_do", "atlas_ph", "atlas_ec", "atlas_rtd",
        }
        incoming_required = {
            str(fluid.get("id")): fluid
            for fluid in msg.get("dosing_fluids", [])
            if isinstance(fluid, dict) and fluid.get("id") in {"ph_up", "ph_down"}
        }
        dosing_fluids = []
        for fluid_id, default_name in (("ph_up", "pH+"), ("ph_down", "pH−")):
            fluid = incoming_required.get(fluid_id, {})
            dosing_fluids.append({
                "id": fluid_id,
                "name": str(fluid.get("name") or default_name)[:64],
                "brand": str(fluid.get("brand") or "Belirtilmedi")[:64],
                "category": "ph",
                "catalog_id": str(fluid.get("catalog_id") or "")[:96],
                "line": str(fluid.get("line") or "")[:64],
                "part": str(fluid.get("part") or "")[:32],
                "npk": str(fluid.get("npk") or "")[:32],
                "phase": str(fluid.get("phase") or "")[:32],
                "medium": str(fluid.get("medium") or "")[:32],
                "ph_direction": str(fluid.get("ph_direction") or "")[:8],
                "required": True,
            })
        fluid_ids = {"ph_up", "ph_down"}
        for fluid in msg.get("dosing_fluids", []):
            fluid_id = str(fluid.get("id") or "")[:48]
            if not fluid_id or fluid_id in fluid_ids:
                continue
            if not fluid_id.replace("_", "").isalnum():
                raise ValueError(f"Invalid dosing fluid id: {fluid_id}")
            fluid_ids.add(fluid_id)
            dosing_fluids.append({
                "id": fluid_id,
                "name": str(fluid.get("name") or fluid_id)[:64],
                "brand": str(fluid.get("brand") or "Özel")[:64],
                "category": str(fluid.get("category") or "other")[:32],
                "catalog_id": str(fluid.get("catalog_id") or "")[:96],
                "line": str(fluid.get("line") or "")[:64],
                "part": str(fluid.get("part") or "")[:32],
                "npk": str(fluid.get("npk") or "")[:32],
                "phase": str(fluid.get("phase") or "")[:32],
                "medium": str(fluid.get("medium") or "")[:32],
                "ph_direction": str(fluid.get("ph_direction") or "")[:8],
                "required": False,
            })
        for item in msg.get("device_assignments", []):
            address = _address(item.get("address"))
            driver = str(item.get("driver") or "")
            if driver not in allowed_drivers:
                raise ValueError(f"Unsupported I2C driver: {driver}")
            if address in assigned:
                continue
            assigned.add(address)
            assignment = {
                "address": address,
                "driver": driver,
                "name": str(item.get("name") or f"I2C 0x{address:02X}")[:64],
            }
            if driver == "waveshare_motor_hat":
                incoming_channels = {
                    str(channel.get("id", "")).upper(): channel
                    for channel in item.get("channels", [])
                    if isinstance(channel, dict)
                }
                channels = []
                for channel_id in ("A", "B"):
                    channel = incoming_channels.get(channel_id, {})
                    fluid_id = str(
                        channel.get("fluid_id") or channel.get("role") or "unassigned"
                    )
                    if fluid_id != "unassigned" and fluid_id not in fluid_ids:
                        raise ValueError(f"Unknown dosing fluid: {fluid_id}")
                    calibration = _motor_calibration(channel.get("calibration"))
                    channels.append({
                        "id": channel_id,
                        "name": str(channel.get("name") or f"Motor {channel_id}")[:64],
                        "fluid_id": fluid_id,
                        "pump": _pump_profile(channel.get("pump")),
                        "calibration": calibration,
                        "calibration_status": "measured" if calibration else "unverified",
                    })
                assignment["channels"] = channels
            assignments.append(assignment)
    except (TypeError, ValueError, AttributeError) as err:
        connection.send_error(msg["id"], "invalid_assignment", str(err))
        return
    store = hass.data[DOMAIN]["store"]
    hardware = await store.async_update_hardware(
        {
            "poll_interval": msg["poll_interval"],
            "device_assignments": assignments,
            "dosing_fluids": dosing_fluids,
            "dosing_policy": _dosing_policy(msg.get("dosing_policy")),
        }
    )
    coordinator = hass.data[DOMAIN].get("atlas_i2c")
    if coordinator is not None:
        try:
            await coordinator.async_reconfigure(hardware)
            from .sensor import async_sync_atlas_entities
            await async_sync_atlas_entities(hass, hass.data[DOMAIN]["entry"])
        except (OSError, ValueError, RuntimeError) as err:
            connection.send_error(msg["id"], "hardware_refresh_failed", str(err))
            return
    connection.send_result(msg["id"], {"hardware": hardware, "reloading": False})


def _dosing_policy(value) -> dict:
    """Validate the future closed-loop dosing order and safety intervals."""
    value = value if isinstance(value, dict) else {}
    return {
        "nutrient_interval_minutes": max(30, min(1440, int(value.get("nutrient_interval_minutes", DEFAULT_DOSING_POLICY["nutrient_interval_minutes"])))),
        "mixing_wait_minutes": max(5, min(180, int(value.get("mixing_wait_minutes", DEFAULT_DOSING_POLICY["mixing_wait_minutes"])))),
        "remeasure_wait_minutes": max(1, min(60, int(value.get("remeasure_wait_minutes", DEFAULT_DOSING_POLICY["remeasure_wait_minutes"])))),
        "ph_interval_minutes": max(10, min(360, int(value.get("ph_interval_minutes", DEFAULT_DOSING_POLICY["ph_interval_minutes"])))),
        "ph_deadband": max(0.02, min(1.0, round(float(value.get("ph_deadband", DEFAULT_DOSING_POLICY["ph_deadband"])), 2))),
        "max_nutrient_dose_ml": max(0.1, min(500.0, round(float(value.get("max_nutrient_dose_ml", DEFAULT_DOSING_POLICY["max_nutrient_dose_ml"])), 2))),
        "max_ph_dose_ml": max(0.1, min(50.0, round(float(value.get("max_ph_dose_ml", DEFAULT_DOSING_POLICY["max_ph_dose_ml"])), 2))),
        "ph_single_direction": True,
        "sequence": "nutrients_mix_remeasure_ph",
    }


def _motor_calibration(value) -> dict | None:
    """Validate a measured pump calibration persisted by the panel."""
    if not isinstance(value, dict):
        return None
    seconds = float(value.get("seconds", 0))
    volume_ml = float(value.get("volume_ml", 0))
    speed = int(value.get("speed", 100))
    if not 1 <= seconds <= 30 or not 0 < volume_ml <= 500 or not 20 <= speed <= 100:
        raise ValueError("Invalid motor calibration measurement")
    return {
        "seconds": round(seconds, 2),
        "volume_ml": round(volume_ml, 3),
        "speed": speed,
        "flow_ml_s": round(volume_ml / seconds, 5),
        "calibrated_at": str(value.get("calibrated_at") or "")[:40],
    }


def _pump_profile(value) -> dict:
    """Validate the physical load attached to one Waveshare channel."""
    if not isinstance(value, dict):
        value = {
            "catalog_id": "nkp_dcl_s10y",
            "brand": "NKP",
            "model": "NKP-DCL-S10Y",
            "pump_type": "peristaltic_dc",
            "voltage": 12,
            "power_w": 5,
            "current_a": 0.417,
            "pwm": True,
            "reversible": True,
        }
    voltage = float(value.get("voltage", 0))
    power_w = float(value.get("power_w", 0))
    current_a = float(value.get("current_a") or (power_w / voltage if voltage else 0))
    if not 6 <= voltage <= 12:
        raise ValueError("Waveshare pump voltage must be between 6 and 12 V")
    if not 0 < current_a <= 1.2:
        raise ValueError("Pump current exceeds the Waveshare 1.2 A channel limit")
    return {
        "catalog_id": str(value.get("catalog_id") or "custom")[:64],
        "brand": str(value.get("brand") or "Özel")[:64],
        "model": str(value.get("model") or "DC peristaltik pompa")[:96],
        "pump_type": "peristaltic_dc",
        "voltage": round(voltage, 2),
        "power_w": round(power_w, 3),
        "current_a": round(current_a, 3),
        "flow_min_ml_min": round(float(value.get("flow_min_ml_min", 0)), 2),
        "flow_max_ml_min": round(float(value.get("flow_max_ml_min", 0)), 2),
        "pwm": bool(value.get("pwm", True)),
        "reversible": bool(value.get("reversible", True)),
        "verified": bool(value.get("verified", False)),
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/hardware/motor_test",
        vol.Required("address"): vol.Any(int, str),
        vol.Required("channel"): vol.In(("A", "B")),
        vol.Required("seconds"): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
        vol.Required("speed"): vol.All(vol.Coerce(int), vol.Range(min=20, max=100)),
        vol.Required("confirmed"): True,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_motor_test(hass, connection, msg) -> None:
    """Run one short, confirmed pump test; the driver always stops afterward."""
    try:
        address = _address(msg["address"])
        await hass.data[DOMAIN]["atlas_i2c"].async_motor_test(
            address, msg["channel"], msg["seconds"], msg["speed"]
        )
    except (TypeError, ValueError, OSError, RuntimeError) as err:
        connection.send_error(msg["id"], "motor_test_failed", str(err))
        return
    connection.send_result(msg["id"], {
        "address": address,
        "channel": msg["channel"],
        "seconds": msg["seconds"],
        "speed": msg["speed"],
        "stopped": True,
    })


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/hardware/calibration_status",
        vol.Required("address"): vol.Any(int, str),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_calibration_status(hass, connection, msg) -> None:
    """Read one Atlas circuit's calibration status."""
    try:
        address = _address(msg["address"])
        status = await hass.data[DOMAIN]["atlas_i2c"].async_calibration_status(address)
    except (TypeError, ValueError, OSError, RuntimeError) as err:
        connection.send_error(msg["id"], "calibration_status_failed", str(err))
        return
    connection.send_result(msg["id"], {"address": address, "status": status})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/hardware/calibrate",
        vol.Required("address"): vol.Any(int, str),
        vol.Required("operation"): str,
        vol.Optional("value"): vol.Any(int, float),
        vol.Required("confirmed"): True,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_calibrate(hass, connection, msg) -> None:
    """Run an explicitly confirmed and driver-validated calibration."""
    try:
        address = _address(msg["address"])
        result = await hass.data[DOMAIN]["atlas_i2c"].async_calibrate(
            address, msg["operation"], msg.get("value")
        )
    except (TypeError, ValueError, OSError, RuntimeError) as err:
        connection.send_error(msg["id"], "calibration_failed", str(err))
        return
    connection.send_result(msg["id"], {"address": address, "result": result})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/hardware/atlas_command",
        vol.Required("address"): vol.Any(int, str),
        vol.Required("command"): str,
        vol.Required("confirmed"): True,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_atlas_command(hass, connection, msg) -> None:
    """Run an explicitly confirmed Atlas management command."""
    try:
        address = _address(msg["address"])
        result = await hass.data[DOMAIN]["atlas_i2c"].async_device_command(
            address, msg["command"]
        )
    except (TypeError, ValueError, OSError, RuntimeError) as err:
        connection.send_error(msg["id"], "atlas_command_failed", str(err))
        return
    connection.send_result(
        msg["id"], {"address": address, "command": msg["command"], "result": result}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hydroponic_system/hardware/atlas_change_address",
        vol.Required("address"): vol.Any(int, str),
        vol.Required("new_address"): vol.Any(int, str),
        vol.Required("confirmed"): True,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_atlas_change_address(hass, connection, msg) -> None:
    """Change an Atlas address and its persisted assignment as one workflow."""
    try:
        old_address = _address(msg["address"])
        new_address = _address(msg["new_address"])
        if old_address == new_address:
            raise ValueError("New address is identical to the current address")
        store = hass.data[DOMAIN]["store"]
        assignments = store.data.get("hardware", {}).get("device_assignments", [])
        if any(int(item.get("address", -1)) == new_address for item in assignments):
            raise ValueError(f"I2C address 0x{new_address:02X} is already assigned")
        await hass.data[DOMAIN]["atlas_i2c"].async_change_address(
            old_address, new_address
        )
        for item in assignments:
            if int(item.get("address", -1)) == old_address:
                item["address"] = new_address
                break
        else:
            raise ValueError(f"No saved assignment exists at 0x{old_address:02X}")
        await store.async_save()
        coordinator = hass.data[DOMAIN]["atlas_i2c"]
        await coordinator.async_reconfigure(store.data.get("hardware", {}))
        from .sensor import async_sync_atlas_entities
        await async_sync_atlas_entities(hass, hass.data[DOMAIN]["entry"])
    except (TypeError, ValueError, OSError, RuntimeError) as err:
        connection.send_error(msg["id"], "atlas_address_change_failed", str(err))
        return
    connection.send_result(
        msg["id"], {"old_address": old_address, "new_address": new_address, "reloading": False}
    )


def async_register(hass: HomeAssistant) -> None:
    """Register WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_get_config)
    websocket_api.async_register_command(hass, websocket_save_entities)
    websocket_api.async_register_command(hass, websocket_save_profile)
    websocket_api.async_register_command(hass, websocket_save_system_profile)
    websocket_api.async_register_command(hass, websocket_save_assistant_settings)
    websocket_api.async_register_command(hass, websocket_generate_assistant_report)
    websocket_api.async_register_command(hass, websocket_select_stage)
    websocket_api.async_register_command(hass, websocket_start_cultivation)
    websocket_api.async_register_command(hass, websocket_finish_cultivation)
    websocket_api.async_register_command(hass, websocket_add_cultivation_event)
    websocket_api.async_register_command(hass, websocket_export_cultivations)
    websocket_api.async_register_command(hass, websocket_save_hardware)
    websocket_api.async_register_command(hass, websocket_motor_test)
    websocket_api.async_register_command(hass, websocket_calibration_status)
    websocket_api.async_register_command(hass, websocket_calibrate)
    websocket_api.async_register_command(hass, websocket_atlas_command)
    websocket_api.async_register_command(hass, websocket_atlas_change_address)
