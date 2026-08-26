"""Normalize live measurements and evaluate sensor trust deterministically.

This module is deliberately read-only.  It does not call services or make control
decisions; it only turns Home Assistant and native I2C readings into an explainable
health snapshot for the panel and future assistant tools.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from statistics import fmean
from typing import Any


DEFAULT_SENSOR_HEALTH_SETTINGS: dict[str, Any] = {
    "default_stale_after_seconds": 300,
    "calibration_due_days": 30,
    "sensors": {},
}


MEASUREMENT_SPECS: dict[str, dict[str, Any]] = {
    "temperature": {
        "label": "Ortam sıcaklığı",
        "entity_key": "temperature_sensors",
        "unit": "°C",
        "target_field": "day_temperature",
        "tolerance": 2.0,
        "spike_threshold": 4.0,
        "divergence_threshold": 3.0,
    },
    "humidity": {
        "label": "Bağıl nem",
        "entity_key": "humidity_sensors",
        "unit": "%",
        "target_field": "humidity",
        "tolerance": 7.0,
        "spike_threshold": 15.0,
        "divergence_threshold": 10.0,
    },
    "vpd": {
        "label": "VPD",
        "entity_key": "vpd_sensor",
        "unit": "kPa",
        "target_field": "vpd",
        "tolerance": 0.25,
        "spike_threshold": 0.45,
        "divergence_threshold": 0.35,
    },
    "co2": {
        "label": "CO₂",
        "entity_key": "co2_sensors",
        "unit": "ppm",
        "target_field": "co2",
        "tolerance": 200.0,
        "spike_threshold": 500.0,
        "divergence_threshold": 300.0,
    },
    "nutrient": {
        "label": "Besin yoğunluğu",
        "entity_key": "ppm_sensor",
        "unit": "ppm",
        "target_field": "ppm",
        "tolerance": 120.0,
        "spike_threshold": 300.0,
        "divergence_threshold": 200.0,
        "calibration_sensitive": True,
    },
    "water_temperature": {
        "label": "Su sıcaklığı",
        "entity_key": "water_temperature_sensor",
        "unit": "°C",
        "target_field": "water_temperature",
        "tolerance": 2.0,
        "spike_threshold": 4.0,
        "divergence_threshold": 2.5,
        "calibration_sensitive": True,
    },
    "ph": {
        "label": "pH",
        "entity_key": "ph_sensor",
        "unit": "pH",
        "target_field": "ph",
        "tolerance": 0.3,
        "spike_threshold": 0.8,
        "divergence_threshold": 0.5,
        "calibration_sensitive": True,
    },
    "dissolved_oxygen": {
        "label": "Suda çözünmüş oksijen",
        "entity_key": "do_sensor",
        "unit": "mg/L",
        "target_field": "do_minimum",
        "minimum_only": True,
        "spike_threshold": 3.0,
        "divergence_threshold": 2.0,
        "calibration_sensitive": True,
    },
}


NATIVE_MEASUREMENT_MAP = {
    "ph": ("ph", 0, "pH"),
    "do": ("dissolved_oxygen", 0, "mg/L"),
    "rtd": ("water_temperature", 0, "°C"),
}


ISSUE_PENALTIES = {
    "unavailable": 100,
    "invalid_value": 100,
    "stale": 55,
    "spike": 25,
    "divergence": 20,
    "unit_mismatch": 40,
    "calibration_unknown": 10,
    "calibration_overdue": 20,
}


def _as_utc(value: Any, fallback: datetime) -> datetime:
    """Parse a datetime-like value and always return an aware UTC datetime."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
    else:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return [value] if isinstance(value, str) and value else []


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _state_source(hass: Any, entity_id: str) -> dict[str, Any]:
    """Copy the small state subset required by the pure evaluator."""
    state = hass.states.get(entity_id)
    if state is None:
        return {
            "id": entity_id,
            "entity_id": entity_id,
            "name": entity_id,
            "source": "home_assistant",
            "state": "unavailable",
        }
    attributes = dict(getattr(state, "attributes", {}) or {})
    return {
        "id": entity_id,
        "entity_id": entity_id,
        "name": attributes.get("friendly_name") or entity_id,
        "source": attributes.get("source") or "home_assistant",
        "state": getattr(state, "state", None),
        "unit": attributes.get("unit_of_measurement"),
        "updated_at": getattr(state, "last_updated", None),
        "attribute_calibrated_at": (
            attributes.get("calibrated_at") or attributes.get("last_calibration")
        ),
        "i2c_address": attributes.get("i2c_address"),
        "i2c_bus": attributes.get("i2c_bus"),
    }


def collect_sources(
    hass: Any, entities: dict[str, Any], atlas: Any = None
) -> dict[str, list[dict[str, Any]]]:
    """Collect configured HA entities and enrolled Atlas channels without duplicates."""
    result: dict[str, list[dict[str, Any]]] = {
        key: [] for key in MEASUREMENT_SPECS
    }
    seen: set[tuple[str, str]] = set()
    for key, spec in MEASUREMENT_SPECS.items():
        for entity_id in _ids(entities.get(spec["entity_key"])):
            item = _state_source(hass, entity_id)
            if item.get("source") == "native_i2c" and item.get("i2c_address"):
                item["id"] = (
                    f"atlas_i2c:{item.get('i2c_bus', getattr(atlas, 'bus_number', 1))}:"
                    f"{item['i2c_address']}:{key}"
                )
            source_id = item["id"]
            identity = (key, source_id)
            if identity in seen:
                continue
            seen.add(identity)
            result[key].append(item)

    if atlas is not None:
        assignments = getattr(atlas, "assignments", {}) or {}
        data = getattr(atlas, "data", {}) or {}
        for device in getattr(atlas, "devices", []) or []:
            device_type = str(device.device_type).lower()
            values = data.get(device.key, {}).get("values", ())
            if device_type == "ec":
                # EZO-EC normally exposes TDS as channel 2.  Never silently compare
                # raw conductivity against a PPM target when TDS output is disabled.
                index = 1 if len(values) > 1 else 0
                measurement_key, unit = "nutrient", "ppm" if index == 1 else "µS/cm"
            elif device_type in NATIVE_MEASUREMENT_MAP:
                measurement_key, index, unit = NATIVE_MEASUREMENT_MAP[device_type]
            else:
                continue
            payload = data.get(device.key, {})
            assignment = assignments.get(device.address, {})
            source_id = (
                f"atlas_i2c:{getattr(atlas, 'bus_number', 1)}:"
                f"0x{device.address:02x}:{measurement_key}"
            )
            identity = (measurement_key, source_id)
            if identity in seen:
                continue
            seen.add(identity)
            result[measurement_key].append({
                "id": source_id,
                "name": assignment.get("name") or f"Atlas EZO {device.device_type}",
                "source": "native_i2c",
                "state": values[index] if index < len(values) else "unavailable",
                "unit": unit,
                "updated_at": payload.get("observed_at"),
                "i2c_address": f"0x{device.address:02x}",
            })

    # Prefer a mapped VPD sensor.  Otherwise expose the exact derived value and
    # age of its oldest input instead of pretending it is a physical probe.
    if not result["vpd"]:
        temperature = [_number(item.get("state")) for item in result["temperature"]]
        humidity = [_number(item.get("state")) for item in result["humidity"]]
        temperature = [value for value in temperature if value is not None]
        humidity = [value for value in humidity if value is not None]
        if temperature and humidity:
            temp = fmean(temperature)
            rh = fmean(humidity)
            vpd = 0.6108 * math.exp((17.27 * temp) / (temp + 237.3)) * (1 - rh / 100)
            timestamps = [
                _as_utc(item.get("updated_at"), datetime.now(timezone.utc))
                for key in ("temperature", "humidity")
                for item in result[key]
                if item.get("updated_at") is not None
            ]
            result["vpd"].append({
                "id": "computed:vpd",
                "name": "Sıcaklık ve nemden hesaplanan VPD",
                "source": "computed",
                "state": vpd,
                "unit": "kPa",
                "updated_at": min(timestamps) if timestamps else None,
            })
    return result


def _calibration(
    source: dict[str, Any],
    settings: dict[str, Any],
    now: datetime,
    sensitive: bool,
) -> tuple[str | None, int | None, list[str]]:
    sensor_settings = settings.get("sensors", {}).get(source["id"], {})
    value = sensor_settings.get("calibrated_at") or source.get("attribute_calibrated_at")
    if not value:
        return None, None, ["calibration_unknown"] if sensitive else []
    calibrated = _as_utc(value, now)
    age_days = max(0, (now - calibrated).days)
    due_days = int(
        sensor_settings.get("calibration_due_days")
        or settings.get("calibration_due_days", 30)
    )
    issues = ["calibration_overdue"] if sensitive and age_days > due_days else []
    return str(value), age_days, issues


def _target(spec: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any] | None:
    if not profile or spec.get("target_field") not in profile:
        return None
    value = _number(profile.get(spec["target_field"]))
    if value is None:
        return None
    if spec.get("minimum_only"):
        return {"value": value, "minimum": value, "maximum": None, "kind": "minimum"}
    tolerance = float(spec["tolerance"])
    return {
        "value": value,
        "minimum": round(value - tolerance, 3),
        "maximum": round(value + tolerance, 3),
        "tolerance": tolerance,
        "kind": "band",
    }


def _outside(value: float, target: dict[str, Any]) -> bool:
    minimum, maximum = target.get("minimum"), target.get("maximum")
    return bool(
        (minimum is not None and value < minimum)
        or (maximum is not None and value > maximum)
    )


def evaluate_sensor_health(
    sources: dict[str, list[dict[str, Any]]],
    *,
    profile: dict[str, Any] | None = None,
    active_cultivation: bool = False,
    settings: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate a complete snapshot; runtime only retains short-lived observations."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    settings = {**DEFAULT_SENSOR_HEALTH_SETTINGS, **(settings or {})}
    runtime = runtime if runtime is not None else {}
    samples = runtime.setdefault("samples", {})
    out_since = runtime.setdefault("out_since", {})
    measurements: dict[str, dict[str, Any]] = {}

    for key, spec in MEASUREMENT_SPECS.items():
        evaluated: list[dict[str, Any]] = []
        for raw in sources.get(key, []):
            source_id = str(raw.get("id") or raw.get("entity_id") or "")
            raw_state = raw.get("state")
            issues: list[str] = []
            value = None
            if raw_state is None or str(raw_state).lower() in {
                "unknown", "unavailable", "none", "",
            }:
                issues.append("unavailable")
            else:
                value = _number(raw_state)
                if value is None:
                    issues.append("invalid_value")

            updated = _as_utc(raw.get("updated_at"), now)
            age_seconds = max(0, int((now - updated).total_seconds()))
            source_settings = settings.get("sensors", {}).get(source_id, {})
            stale_after = max(30, int(
                source_settings.get("stale_after_seconds")
                or settings["default_stale_after_seconds"]
            ))
            if value is not None and age_seconds > stale_after:
                issues.append("stale")

            previous = samples.get(source_id)
            if value is not None and previous and previous.get("updated_at") != _iso(updated):
                previous_value = _number(previous.get("value"))
                elapsed = max(0, (
                    updated - _as_utc(previous.get("updated_at"), updated)
                ).total_seconds())
                if (
                    previous_value is not None
                    and elapsed <= max(900, stale_after * 2)
                    and abs(value - previous_value) >= float(spec["spike_threshold"])
                ):
                    issues.append("spike")
            if value is not None:
                samples[source_id] = {"value": value, "updated_at": _iso(updated)}

            calibrated_at, calibration_age_days, calibration_issues = _calibration(
                {**raw, "id": source_id},
                settings,
                now,
                bool(spec.get("calibration_sensitive")),
            )
            issues.extend(calibration_issues)
            confidence = max(
                0,
                100 - sum(ISSUE_PENALTIES.get(issue, 0) for issue in set(issues)),
            )
            if "unavailable" in issues or "invalid_value" in issues:
                status = "unavailable"
            elif "stale" in issues:
                status = "stale"
            elif "spike" in issues:
                status = "suspect"
            else:
                status = "ok"
            evaluated.append({
                "id": source_id,
                "entity_id": raw.get("entity_id"),
                "name": raw.get("name") or source_id,
                "source": raw.get("source") or "home_assistant",
                "value": round(value, 3) if value is not None else None,
                "unit": raw.get("unit") or spec["unit"],
                "updated_at": _iso(updated) if raw.get("updated_at") is not None else None,
                "age_seconds": age_seconds if raw.get("updated_at") is not None else None,
                "stale_after_seconds": stale_after,
                "status": status,
                "issues": list(dict.fromkeys(issues)),
                "confidence": confidence,
                "calibrated_at": calibrated_at,
                "calibration_age_days": calibration_age_days,
                **({"i2c_address": raw["i2c_address"]} if raw.get("i2c_address") else {}),
            })

        comparable = [
            item for item in evaluated
            if item["value"] is not None and item["status"] != "unavailable"
        ]
        unit_groups: dict[str, list[dict[str, Any]]] = {}
        for item in comparable:
            unit_groups.setdefault(item["unit"], []).append(item)
        if len(unit_groups) > 1:
            for item in comparable:
                item["issues"].append("unit_mismatch")
                item["confidence"] = max(
                    0, item["confidence"] - ISSUE_PENALTIES["unit_mismatch"]
                )
                if item["status"] == "ok":
                    item["status"] = "suspect"
        selected = unit_groups.get(spec["unit"])
        if selected is None and unit_groups:
            selected = max(unit_groups.values(), key=len)
        selected = selected or []
        values = [item["value"] for item in selected]
        divergence = None
        if len(values) > 1:
            spread = max(values) - min(values)
            divergence = {
                "spread": round(spread, 3),
                "threshold": spec["divergence_threshold"],
                "detected": spread > float(spec["divergence_threshold"]),
            }
            if divergence["detected"]:
                for item in comparable:
                    if "divergence" not in item["issues"]:
                        item["issues"].append("divergence")
                        item["confidence"] = max(
                            0,
                            item["confidence"] - ISSUE_PENALTIES["divergence"],
                        )
                        if item["status"] == "ok":
                            item["status"] = "suspect"

        usable = [item for item in selected if item["status"] == "ok"]
        aggregate_values = [item["value"] for item in (usable or selected)]
        aggregate_value = round(fmean(aggregate_values), 3) if aggregate_values else None
        unit = (usable or selected)[0]["unit"] if selected else spec["unit"]
        target = _target(spec, profile) if active_cultivation else None
        target_comparable = target is not None and unit == spec["unit"]
        target_outside = bool(
            target_comparable
            and aggregate_value is not None
            and _outside(aggregate_value, target)
        )
        if target_outside:
            out_since.setdefault(key, _iso(now))
        else:
            out_since.pop(key, None)
        outside_seconds = (
            max(0, int((now - _as_utc(out_since[key], now)).total_seconds()))
            if target_outside else 0
        )

        statuses = {item["status"] for item in evaluated}
        if not evaluated or aggregate_value is None:
            status = "unavailable"
        elif "suspect" in statuses:
            status = "suspect"
        elif "stale" in statuses:
            status = "stale"
        else:
            status = "ok"
        confidence = (
            round(fmean([item["confidence"] for item in evaluated]))
            if evaluated else 0
        )
        measurements[key] = {
            "key": key,
            "label": spec["label"],
            "value": aggregate_value,
            "unit": unit,
            "status": status,
            "confidence": confidence,
            "source_count": len(evaluated),
            "available_count": len(comparable),
            "sources": evaluated,
            "divergence": divergence,
            "target": target,
            "target_comparable": target_comparable,
            "target_outside": target_outside,
            "outside_since": out_since.get(key),
            "outside_duration_seconds": outside_seconds,
        }

    items = list(measurements.values())
    trusted = [item for item in items if item["status"] == "ok"]
    overall_confidence = (
        round(fmean([item["confidence"] for item in items])) if items else 0
    )
    attention = sum(
        item["status"] != "ok" or item["target_outside"] for item in items
    )
    return {
        "generated_at": _iso(now),
        "mode": "read_only",
        "summary": {
            "status": "attention" if attention else "healthy",
            "confidence": overall_confidence,
            "measurement_count": len(items),
            "healthy_count": len(trusted),
            "attention_count": attention,
            "unavailable_count": sum(item["status"] == "unavailable" for item in items),
            "stale_count": sum(item["status"] == "stale" for item in items),
            "suspect_count": sum(item["status"] == "suspect" for item in items),
            "target_outside_count": sum(item["target_outside"] for item in items),
        },
        "measurements": measurements,
        "settings": settings,
    }


def sensor_health_snapshot(
    hass: Any,
    entities: dict[str, Any],
    *,
    atlas: Any = None,
    profile: dict[str, Any] | None = None,
    active_cultivation: bool = False,
    settings: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect current sources and return their deterministic health snapshot."""
    return evaluate_sensor_health(
        collect_sources(hass, entities, atlas),
        profile=profile,
        active_cultivation=active_cultivation,
        settings=settings,
        runtime=runtime,
    )
