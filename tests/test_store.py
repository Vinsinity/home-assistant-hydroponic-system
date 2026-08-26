"""Storage-level tests for redundant journal persistence and recovery."""

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).parents[1] / "custom_components/hydroponic_system"


class FakeStore:
    documents = {}

    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, _hass, _version, key):
        self.key = key

    async def async_load(self):
        return deepcopy(self.documents.get(self.key))

    async def async_save(self, value):
        self.documents[self.key] = deepcopy(value)


def _load_store_module():
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    helpers = types.ModuleType("homeassistant.helpers")
    storage = types.ModuleType("homeassistant.helpers.storage")
    storage.Store = FakeStore
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.core": core,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.storage": storage,
        }
    )

    package_name = "_hydroponic_store_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(
        f"{package_name}.store", ROOT / "store.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, sys.modules[f"{package_name}.const"], sys.modules[f"{package_name}.journal"]


store_module, const, journal = _load_store_module()


def test_store_mirrors_then_recovers_an_event_missing_from_primary():
    FakeStore.documents = {}
    store = store_module.HydroponicSystemStore(object())
    asyncio.run(store.async_load())
    record = journal.new_cultivation(
        name="Recovery grow",
        start_date="2026-08-01",
        identity={"plant_species": "Tomato"},
        plan=[{"stage": "germination", "planned_days": 6}],
        cultivation_id="recovery_grow",
        timestamp="2026-08-01T08:00:00+00:00",
    )
    asyncio.run(store.async_start_cultivation(record))
    asyncio.run(
        store.async_append_event(
            event_type="user_note",
            local_date="2026-08-02",
            note="Keep this entry",
            values={},
            event_id="durable_event",
        )
    )

    recovery = FakeStore.documents[const.JOURNAL_RECOVERY_STORAGE_KEY]
    assert recovery["checksum"] == journal.journal_checksum(recovery["payload"])
    assert any(event["id"] == "durable_event" for event in recovery["payload"]["events"])

    # Simulate a stale primary document after the recovery write succeeded.
    primary = FakeStore.documents[const.STORAGE_KEY]
    primary["events"] = [
        event for event in primary["events"] if event["id"] != "durable_event"
    ]
    FakeStore.documents[const.STORAGE_KEY] = primary

    restored = store_module.HydroponicSystemStore(object())
    asyncio.run(restored.async_load())

    assert restored.journal_diagnostic["recovered"] is True
    assert any(event["id"] == "durable_event" for event in restored.data["events"])
    assert any(
        event["id"] == "durable_event"
        for event in FakeStore.documents[const.STORAGE_KEY]["events"]
    )


def test_store_removes_the_old_unmeasured_one_ml_placeholder():
    FakeStore.documents = {
        const.STORAGE_KEY: {
            "hardware": {
                "device_assignments": [
                    {
                        "address": 0x40,
                        "driver": "waveshare_motor_hat",
                        "channels": [
                            {
                                "id": "A",
                                "calibration": {
                                    "seconds": 1.0,
                                    "volume_ml": 1.0,
                                    "speed": 100,
                                    "flow_ml_s": 1.0,
                                    "calibrated_at": "",
                                },
                            }
                        ],
                    }
                ]
            }
        }
    }

    store = store_module.HydroponicSystemStore(object())
    asyncio.run(store.async_load())
    channel = store.data["hardware"]["device_assignments"][0]["channels"][0]

    assert channel["calibration"] is None
    assert channel["calibration_status"] == "unverified"
