"""Standalone SQLite durability and Home Assistant migration tests."""

from copy import deepcopy
import json
import sqlite3

import pytest

from custom_components.hydroponic_system import journal
from growasist.storage import (
    GrowAsistStore,
    ImportChecksumError,
    JournalConflictError,
)


def _record(record_id: str = "pi_grow"):
    return journal.new_cultivation(
        name="Pi grow",
        start_date="2026-08-26",
        identity={"plant_species": "Tomato", "plant_count": 2},
        plan=[{"stage": "germination", "planned_days": 6}],
        cultivation_id=record_id,
        timestamp="2026-08-26T08:00:00+00:00",
    )


def _state_with_event():
    state = {
        "schema_version": journal.JOURNAL_SCHEMA_VERSION,
        "cultivations": journal.empty_cultivations(),
        "events": [],
    }
    journal.start_cultivation(state, _record())
    journal.append_event(
        state,
        journal.make_event(
            event_type="user_note",
            cultivation_id="pi_grow",
            local_date="2026-08-26",
            note="Never lose this",
            data={},
            event_id="permanent_note",
        ),
    )
    return state


def test_standalone_store_survives_restart_and_keeps_wal_integrity(tmp_path):
    database = tmp_path / "growasist.db"
    store = GrowAsistStore(database)
    saved = store.save_state(_state_with_event())

    restarted = GrowAsistStore(database)
    loaded = restarted.load_state()
    health = restarted.health()

    assert loaded["cultivations"] == saved["cultivations"]
    assert any(event["id"] == "permanent_note" for event in loaded["events"])
    assert loaded["active_stage"] == "germination"
    assert loaded["engine_enabled"] is False
    assert health["sqlite_integrity"] == "ok"
    assert health["event_count"] == 3
    assert health["revision_count"] >= 1


def test_saving_stale_state_cannot_delete_an_existing_event(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    first = store.save_state(_state_with_event())
    stale = deepcopy(first)
    stale["events"] = [
        event for event in stale["events"] if event["id"] != "permanent_note"
    ]

    restored = store.save_state(stale)

    assert any(event["id"] == "permanent_note" for event in restored["events"])
    assert store.health()["event_count"] == 3


def test_event_id_cannot_be_reused_with_modified_content(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    saved = store.save_state(_state_with_event())
    changed = deepcopy(saved)
    event = next(item for item in changed["events"] if item["id"] == "permanent_note")
    event["note"] = "Rewritten"

    with pytest.raises(JournalConflictError):
        store.save_state(changed)


def test_sqlite_triggers_reject_direct_event_update_and_delete(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    store.save_state(_state_with_event())

    with sqlite3.connect(store.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE journal_events SET payload = '{}' WHERE event_id = ?",
                ("permanent_note",),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM journal_events WHERE event_id = ?",
                ("permanent_note",),
            )


def test_ha_export_import_merges_and_validates_checksum(tmp_path):
    source = GrowAsistStore(tmp_path / "source.db")
    source_state = _state_with_event()
    source_state["profiles"] = {"bloom": {"name": "Çiçeklenme", "planned_days": 63}}
    source_state["hardware"] = {
        "i2c_bus": 1,
        "poll_interval": 45,
        "dosing_policy": {},
        "device_assignments": [],
        "dosing_fluids": [{"id": "ph_up", "name": "pH+"}, {"id": "ph_down", "name": "pH-"}],
    }
    saved_source = source.save_state(source_state)
    saved_source["grow_profiles"]["records"]["tomato_starter"]["name"] = (
        "Taşınan bağımsız profil"
    )
    source.save_state(saved_source)
    export = source.export_journal()

    target = GrowAsistStore(tmp_path / "target.db")
    imported = target.import_home_assistant_export(export)

    assert "pi_grow" in imported["cultivations"]["records"]
    assert any(event["id"] == "permanent_note" for event in imported["events"])
    assert imported["profiles"]["bloom"]["planned_days"] == 63
    assert (
        imported["grow_profiles"]["records"]["tomato_starter"]["name"]
        == "Taşınan bağımsız profil"
    )
    assert imported["hardware"]["poll_interval"] == 45
    assert imported["engine_enabled"] is False

    corrupt = deepcopy(export)
    corrupt["events"][0]["note"] = "tampered"
    with pytest.raises(ImportChecksumError):
        target.import_home_assistant_export(corrupt)


def test_online_backup_is_a_valid_independent_database(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    store.save_state(_state_with_event())

    backup_path = store.backup(tmp_path / "backup" / "growasist.db")
    backup = GrowAsistStore(backup_path)

    assert backup.health()["ok"] is True
    assert any(
        event["id"] == "permanent_note" for event in backup.load_state()["events"]
    )


def test_manufacturer_catalog_is_persisted_without_replacing_user_fluids(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    state = store.load_state()
    state["hardware"]["dosing_fluids"].append(
        {"id": "my_mix", "name": "My Mix", "category": "base"}
    )
    store.save_state(state)

    restarted = GrowAsistStore(store.database_path).load_state()

    assert len(restarted["nutrient_catalog"]["products"]) >= 367
    assert any(item["id"] == "my_mix" for item in restarted["hardware"]["dosing_fluids"])
    assert restarted["hardware"]["dosing_fluids"][0]["category"] == "ph"


def test_catalog_upgrade_keeps_selected_products_and_immutable_journal(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    state = _state_with_event()
    state["hardware"] = {
        "i2c_bus": 1,
        "poll_interval": 30,
        "dosing_policy": {},
        "device_assignments": [],
        "dosing_fluids": [
            {"id": "ph_up", "name": "pH+"},
            {"id": "ph_down", "name": "pH−"},
            {"id": "my_base", "name": "My Base", "category": "base"},
        ],
    }
    saved = store.save_state(state)
    saved["nutrient_catalog"] = {
        "catalog_version": "old-version",
        "products": {},
    }
    payload = json.dumps(saved, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    checksum = journal.journal_checksum(saved)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE current_state SET payload = ?, checksum = ? WHERE singleton = 1",
            (payload, checksum),
        )

    upgraded_store = GrowAsistStore(store.database_path)
    upgraded = upgraded_store.load_state()

    assert len(upgraded["nutrient_catalog"]["products"]) >= 367
    assert any(item["id"] == "my_base" for item in upgraded["hardware"]["dosing_fluids"])
    assert any(event["id"] == "permanent_note" for event in upgraded["events"])
    assert upgraded_store.health()["event_count"] == 3
