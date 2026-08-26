"""Tests for deterministic, read-only sensor health evaluation."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path


MODULE = Path(__file__).parents[1] / "custom_components/hydroponic_system/sensor_health.py"
SPEC = importlib.util.spec_from_file_location("sensor_health", MODULE)
sensor_health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sensor_health)


NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def source(value, *, source_id="sensor.test", updated_at=NOW, unit="°C"):
    return {
        "id": source_id,
        "name": source_id,
        "source": "home_assistant",
        "state": value,
        "unit": unit,
        "updated_at": updated_at,
    }


def evaluate(sources, **kwargs):
    return sensor_health.evaluate_sensor_health(sources, now=NOW, **kwargs)


def test_current_measurement_reports_value_age_target_and_confidence():
    result = evaluate(
        {"temperature": [source(25, updated_at=NOW - timedelta(seconds=42))]},
        profile={"day_temperature": 25},
        active_cultivation=True,
    )
    measurement = result["measurements"]["temperature"]

    assert measurement["value"] == 25
    assert measurement["status"] == "ok"
    assert measurement["confidence"] == 100
    assert measurement["sources"][0]["age_seconds"] == 42
    assert measurement["target"] == {
        "value": 25.0,
        "minimum": 23.0,
        "maximum": 27.0,
        "tolerance": 2.0,
        "kind": "band",
    }
    assert measurement["target_outside"] is False


def test_unavailable_and_stale_are_distinct_explainable_states():
    result = evaluate({
        "temperature": [source("unavailable", source_id="sensor.offline")],
        "humidity": [source(55, source_id="sensor.old", updated_at=NOW - timedelta(minutes=6), unit="%")],
    })

    offline = result["measurements"]["temperature"]["sources"][0]
    old = result["measurements"]["humidity"]["sources"][0]
    assert offline["status"] == "unavailable"
    assert offline["issues"] == ["unavailable"]
    assert old["status"] == "stale"
    assert "stale" in old["issues"]
    assert old["age_seconds"] == 360


def test_spike_detection_compares_distinct_observations_in_runtime():
    runtime = {}
    earlier = NOW - timedelta(minutes=1)
    sensor_health.evaluate_sensor_health(
        {"ph": [source(5.8, source_id="sensor.ph", updated_at=earlier, unit="pH")]},
        runtime=runtime,
        now=earlier,
    )
    result = evaluate(
        {"ph": [source(7.1, source_id="sensor.ph", updated_at=NOW, unit="pH")]},
        runtime=runtime,
    )

    ph = result["measurements"]["ph"]["sources"][0]
    assert ph["status"] == "suspect"
    assert "spike" in ph["issues"]
    assert ph["confidence"] < 100


def test_multiple_probe_divergence_marks_sources_suspect():
    result = evaluate({
        "water_temperature": [
            source(18, source_id="sensor.water_a"),
            source(22, source_id="sensor.water_b"),
        ]
    })
    measurement = result["measurements"]["water_temperature"]

    assert measurement["divergence"] == {
        "spread": 4.0,
        "threshold": 2.5,
        "detected": True,
    }
    assert measurement["status"] == "suspect"
    assert all("divergence" in item["issues"] for item in measurement["sources"])


def test_target_outside_duration_is_continuous_runtime_state():
    runtime = {}
    earlier = NOW - timedelta(minutes=12)
    sensor_health.evaluate_sensor_health(
        {"temperature": [source(30, updated_at=earlier)]},
        profile={"day_temperature": 25},
        active_cultivation=True,
        runtime=runtime,
        now=earlier,
    )
    result = evaluate(
        {"temperature": [source(30, updated_at=NOW)]},
        profile={"day_temperature": 25},
        active_cultivation=True,
        runtime=runtime,
    )

    measurement = result["measurements"]["temperature"]
    assert measurement["target_outside"] is True
    assert measurement["outside_duration_seconds"] == 720


def test_calibration_metadata_changes_confidence_without_hiding_reading():
    result = evaluate(
        {"ph": [source(5.9, source_id="sensor.ph", unit="pH")]},
        settings={
            "calibration_due_days": 30,
            "sensors": {"sensor.ph": {"calibrated_at": "2026-06-01"}},
        },
    )
    ph = result["measurements"]["ph"]["sources"][0]

    assert ph["value"] == 5.9
    assert ph["status"] == "ok"
    assert "calibration_overdue" in ph["issues"]
    assert ph["confidence"] == 80


def test_raw_ec_is_not_compared_to_a_ppm_profile_target():
    result = evaluate(
        {"nutrient": [source(1200, source_id="atlas", unit="µS/cm")]},
        profile={"ppm": 700},
        active_cultivation=True,
    )
    nutrient = result["measurements"]["nutrient"]

    assert nutrient["unit"] == "µS/cm"
    assert nutrient["target_comparable"] is False
    assert nutrient["target_outside"] is False


def test_mixed_units_are_flagged_and_never_averaged_together():
    result = evaluate({
        "temperature": [
            source(25, source_id="sensor.celsius", unit="°C"),
            source(77, source_id="sensor.fahrenheit", unit="°F"),
        ]
    })
    temperature = result["measurements"]["temperature"]

    assert temperature["value"] == 25
    assert temperature["unit"] == "°C"
    assert temperature["status"] == "suspect"
    assert all(
        "unit_mismatch" in item["issues"] for item in temperature["sources"]
    )
