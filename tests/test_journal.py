"""Tests for the versioned, append-only cultivation journal."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


MODULE = Path(__file__).parents[1] / "custom_components/hydroponic_system/journal.py"
SPEC = importlib.util.spec_from_file_location("journal", MODULE)
journal = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = journal
SPEC.loader.exec_module(journal)


def _data():
    return {
        "schema_version": journal.JOURNAL_SCHEMA_VERSION,
        "active_stage": None,
        "cultivations": journal.empty_cultivations(),
        "events": [],
    }


def _record(record_id: str, start_date: str):
    return journal.new_cultivation(
        name=f"Grow {record_id}",
        start_date=start_date,
        identity={
            "plant_species": "Tomato",
            "cultivar": "Marmande",
            "cultivar_id": "example_marmande",
            "growth_type": "photoperiod",
            "breeder_id": "example_breeder",
            "breeder_name": "Example Breeder",
            "plant_count": 4,
            "growing_method": "RDWC",
            "growing_medium": "Expanded clay",
            "reservoir_volume_l": 80,
        },
        plan=[{"stage": "germination", "planned_days": 6}],
        system_snapshot={
            "cabin": {"name": "Cabinet A"},
            "lighting": {"model": "Fixture 1"},
        },
        plant_snapshot={
            "id": "tomato",
            "name": "Tomato",
        },
        grow_profile_snapshot={
            "id": "summer_rdwc",
            "name": "Summer RDWC",
            "stages": {"germination": {"planned_days": 6}},
        },
        genetics_snapshot={
            "growth_type": {"id": "photoperiod", "name": "Photoperiod"},
            "breeder": {"id": "example_breeder", "name": "Example Breeder"},
            "cultivar": {"id": "example_marmande", "name": "Marmande"},
        },
        nutrient_program_snapshot={
            "name": "Base program",
            "nutrient_ids": ["base_a", "base_b"],
            "products": [
                {"id": "base_a", "name": "Base A"},
                {"id": "base_b", "name": "Base B"},
            ],
        },
        iot_snapshot={
            "schema_version": 1,
            "devices": [{"id": "shelly-light", "role": "light_dimmer"}],
        },
        i2c_snapshot={
            "schema_version": 1,
            "i2c_bus": 1,
            "device_assignments": [{"address": 0x63, "driver": "atlas_ph"}],
        },
        cultivation_id=record_id,
        timestamp=f"{start_date}T08:00:00+00:00",
    )


def test_new_cultivation_never_replaces_finished_history():
    data = _data()
    first = journal.start_cultivation(data, _record("grow_one", "2026-08-01"))
    journal.append_event(
        data,
        journal.make_event(
            event_type="user_note",
            cultivation_id=first["id"],
            local_date="2026-08-02",
            note="Roots visible",
            data={},
            event_id="note_one",
        ),
    )
    journal.finish_cultivation(data, local_date="2026-08-03")
    first_snapshot = deepcopy(data["cultivations"]["records"]["grow_one"])
    first_event_ids = {
        event["id"] for event in data["events"] if event["cultivation_id"] == "grow_one"
    }

    journal.start_cultivation(data, _record("grow_two", "2026-08-04"))

    assert data["cultivations"]["active_id"] == "grow_two"
    assert data["cultivations"]["order"] == ["grow_one", "grow_two"]
    assert data["cultivations"]["records"]["grow_one"] == first_snapshot
    assert first_event_ids <= {event["id"] for event in data["events"]}


def test_cultivation_keeps_its_system_snapshot_in_record_and_start_event():
    data = _data()
    record = journal.start_cultivation(data, _record("grow", "2026-08-01"))

    assert record["system_snapshot"]["cabin"]["name"] == "Cabinet A"
    started = next(event for event in data["events"] if event["type"] == "cultivation_started")
    assert started["data"]["system_snapshot"] == record["system_snapshot"]
    assert record["plant_snapshot"]["id"] == "tomato"
    assert started["data"]["plant_snapshot"] == record["plant_snapshot"]
    assert record["grow_profile_snapshot"]["id"] == "summer_rdwc"
    assert started["data"]["grow_profile_snapshot"] == record["grow_profile_snapshot"]
    assert record["genetics_snapshot"]["breeder"]["name"] == "Example Breeder"
    assert started["data"]["genetics_snapshot"] == record["genetics_snapshot"]
    assert record["nutrient_program_snapshot"]["nutrient_ids"] == ["base_a", "base_b"]
    assert started["data"]["nutrient_program_snapshot"] == record["nutrient_program_snapshot"]
    assert record["iot_snapshot"]["devices"][0]["id"] == "shelly-light"
    assert started["data"]["iot_snapshot"] == record["iot_snapshot"]
    assert record["i2c_snapshot"]["device_assignments"][0]["address"] == 0x63
    assert started["data"]["i2c_snapshot"] == record["i2c_snapshot"]
    assert record["identity"]["cultivar_id"] == "example_marmande"
    assert record["identity"]["growing_medium"] == "Expanded clay"


def test_legacy_embedded_plant_profile_is_split_into_two_snapshots():
    legacy = {
        "schema_version": 6,
        "cultivations": {
            "active_id": "legacy",
            "order": ["legacy"],
            "records": {
                "legacy": {
                    "id": "legacy",
                    "name": "Legacy",
                    "active": True,
                    "start_date": "2026-08-01",
                    "identity": {"plant_profile_id": "tomato", "plant_species": "Tomato"},
                    "plan": [{"stage": "germination", "planned_days": 6}],
                    "transitions": [{"stage": "germination", "date": "2026-08-01"}],
                    "plant_profile_snapshot": {
                        "id": "tomato",
                        "name": "Tomato",
                        "profile": {
                            "kind": "editable_example",
                            "stages": {"germination": {"planned_days": 6}},
                            "references": ["https://example.test/reference"],
                        },
                    },
                }
            },
        },
        "events": [],
    }

    migrated, changed = journal.migrate_journal(legacy)
    record = migrated["cultivations"]["records"]["legacy"]

    assert changed is True
    assert record["identity"]["plant_id"] == "tomato"
    assert "plant_profile_id" not in record["identity"]
    assert record["plant_snapshot"]["id"] == "tomato"
    assert "profile" not in record["plant_snapshot"]
    assert record["grow_profile_snapshot"]["stages"]["germination"]["planned_days"] == 6
    assert "plant_profile_snapshot" not in record


def test_selected_enabled_plant_stage_becomes_initial_stage():
    data = _data()
    record = journal.new_cultivation(
        name="Transplant grow",
        start_date="2026-08-01",
        identity={"plant_species": "Lettuce"},
        plan=[{"stage": "early_veg", "planned_days": 7}, {"stage": "veg", "planned_days": 21}],
        initial_stage="veg",
        cultivation_id="transplant",
        timestamp="2026-08-01T08:00:00+00:00",
    )

    journal.start_cultivation(data, record)

    assert data["active_stage"] == "veg"
    assert record["transitions"][0]["stage"] == "veg"
    transition = next(event for event in data["events"] if event["type"] == "stage_transition")
    assert transition["data"]["stage"] == "veg"


def test_initial_stage_must_exist_in_enabled_plan():
    with pytest.raises(ValueError, match="Initial stage"):
        journal.new_cultivation(
            name="Invalid stage",
            start_date="2026-08-01",
            identity={"plant_species": "Lettuce"},
            plan=[{"stage": "germination", "planned_days": 7}],
            initial_stage="bloom",
        )


def test_events_are_append_only_and_duplicate_ids_are_rejected():
    data = _data()
    journal.start_cultivation(data, _record("grow", "2026-08-01"))
    event = journal.make_event(
        event_type="maintenance",
        cultivation_id="grow",
        local_date="2026-08-01",
        note="Cleaned filter",
        data={},
        event_id="fixed_event",
    )
    journal.append_event(data, event)
    with pytest.raises(ValueError):
        journal.append_event(data, event)
    assert [item["id"] for item in data["events"]].count("fixed_event") == 1


def test_legacy_single_cultivation_and_daily_payload_are_preserved():
    legacy_entry = {
        "note": "First roots",
        "photos": [{"url": "https://example.test/root.jpg", "caption": "Root"}],
        "unknown_future_field": {"keep": True},
    }
    stored = {
        "active_stage": "germination",
        "cultivation": {
            "active": True,
            "id": "legacy_grow",
            "name": "Legacy grow",
            "start_date": "2026-08-01",
            "started_at": "2026-08-01T08:00:00+00:00",
            "completed_at": "",
            "plan": [{"stage": "germination", "planned_days": 6}],
            "transitions": [{"stage": "germination", "date": "2026-08-01"}],
            "journal": {"2026-08-02": legacy_entry},
        },
        "calendar": {"journal": {"2026-08-03": {"note": "System note"}}},
    }

    migrated, changed = journal.migrate_journal(stored)

    assert changed is True
    assert migrated["cultivations"]["active_id"] == "legacy_grow"
    record = migrated["cultivations"]["records"]["legacy_grow"]
    assert record["legacy_journal"]["2026-08-02"] == legacy_entry
    assert {event["type"] for event in migrated["events"]} >= {
        "cultivation_started",
        "stage_transition",
        "legacy_import",
        "photo",
    }
    imported_entries = [
        event["data"]["entry"]
        for event in migrated["events"]
        if event["type"] == "legacy_import"
    ]
    assert legacy_entry in imported_entries
    assert {"note": "System note"} in imported_entries


def test_recovery_merge_restores_missing_record_and_event():
    primary = _data()
    recovery = _data()
    journal.start_cultivation(recovery, _record("recovered", "2026-08-01"))

    merged, changed = journal.merge_journal_recovery(primary, recovery)

    assert changed is True
    assert merged["cultivations"]["active_id"] == "recovered"
    assert "recovered" in merged["cultivations"]["records"]
    assert len(merged["events"]) == 2


def test_checksums_detect_modified_exports():
    payload = {"cultivations": journal.empty_cultivations(), "events": []}
    checksum = journal.journal_checksum(payload)
    payload["events"].append({"id": "changed"})
    assert journal.journal_checksum(payload) != checksum


def test_old_synthetic_calibration_is_not_treated_as_measured():
    placeholder = {
        "seconds": 1.0,
        "volume_ml": 1.0,
        "speed": 100,
        "flow_ml_s": 1.0,
        "calibrated_at": "",
    }
    measured = {**placeholder, "calibrated_at": "2026-08-20T12:00:00+00:00"}
    assert journal.is_unverified_legacy_calibration(placeholder) is True
    assert journal.is_unverified_legacy_calibration(measured) is False


def test_identity_values_are_bounded_and_normalized():
    identity = journal.normalize_identity(
        {"plant_count": 0, "reservoir_volume_l": -5, "system_volume_l": 120.45678}
    )
    assert identity["plant_count"] == 1
    assert identity["reservoir_volume_l"] == 0
    assert identity["system_volume_l"] == 120.457


def test_user_event_payloads_are_strict_and_normalized():
    assert journal.normalize_user_event_values(
        "water_added", {"amount": "12.34567", "unit": "L", "ignored": True}
    ) == {"amount": 12.3457, "unit": "L"}
    assert journal.normalize_user_event_values(
        "photo", {"url": "https://example.test/photo.jpg"}
    ) == {"url": "https://example.test/photo.jpg"}
    with pytest.raises(ValueError):
        journal.normalize_user_event_values("nutrient_dose", {"amount": 2, "unit": "L"})
    with pytest.raises(ValueError):
        journal.normalize_user_event_values("photo", {"url": "javascript:alert(1)"})


def test_large_or_malformed_legacy_data_is_preserved_without_blocking_migration():
    long_note = "x" * 20_000
    stored = {
        "cultivation": {
            "active": True,
            "id": "legacy_large",
            "name": "Legacy",
            "start_date": "not-a-date",
            "identity": {"plant_count": "unknown", "reservoir_volume_l": "bad"},
            "journal": {"also-not-a-date": {"note": long_note}},
        }
    }

    migrated, _changed = journal.migrate_journal(stored)

    record = migrated["cultivations"]["records"]["legacy_large"]
    assert record["legacy_journal"]["also-not-a-date"]["note"] == long_note
    assert record["identity"]["plant_count"] == 1
    assert any(
        event["data"].get("entry", {}).get("note") == long_note
        for event in migrated["events"]
        if event["type"] == "legacy_import"
    )
