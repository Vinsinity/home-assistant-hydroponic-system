"""Standalone service and authenticated web API tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from threading import Thread

import pytest

from growasist.server import build_handler
from growasist.service import GrowAsistService
from growasist.storage import GrowAsistStore


def _start_payload(**overrides):
    return {
        "cultivation_id": "standalone_grow",
        "name": "Standalone grow",
        "start_date": date.today().isoformat(),
        "plant_id": "tomato",
        "grow_profile_id": "extended_fruiting",
        "plant_count": 2,
        "growing_method": "RDWC",
        "growing_medium": "Expanded clay",
        "nutrient_program": "Test program",
        **overrides,
    }


def test_service_tracks_a_complete_grow_without_home_assistant(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    service = GrowAsistService(store)

    started = service.start_cultivation(_start_payload())
    bootstrap = service.bootstrap()

    assert started["identity"]["plant_species"] == "Domates"
    assert bootstrap["mode"] == "standalone"
    assert bootstrap["engine_enabled"] is False
    assert bootstrap["active_cultivation"]["id"] == "standalone_grow"
    assert [event["type"] for event in bootstrap["events"]] == [
        "cultivation_started",
        "stage_transition",
    ]

    note = service.append_journal_event(
        {
            "event_id": "permanent_water_note",
            "type": "water_added",
            "local_date": date.today().isoformat(),
            "note": "Rezervuar tamamlandı",
            "values": {"amount": 5, "unit": "L"},
        }
    )
    assert note["data"] == {"amount": 5.0, "unit": "L"}

    restarted = GrowAsistService(GrowAsistStore(store.database_path))
    assert any(
        event["id"] == "permanent_water_note"
        for event in restarted.bootstrap()["events"]
    )

    restarted.finish_cultivation({"local_date": date.today().isoformat()})
    archived = restarted.bootstrap()
    assert archived["active_cultivation"] is None
    assert archived["active_stage"] is None
    assert any(event["type"] == "cultivation_finished" for event in archived["events"])
    assert archived["storage"]["event_count"] == 4


def test_custom_plant_is_persisted_in_the_library(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))

    grow = service.start_cultivation(
        _start_payload(
            cultivation_id="custom_grow",
            plant_id="",
            plant_species="Pak choi",
        )
    )
    restarted = service.bootstrap()

    custom_id = grow["identity"]["plant_id"]
    assert custom_id.startswith("custom_")
    assert restarted["plant_catalog"]["records"][custom_id]["name"] == "Pak choi"


def test_later_setup_edits_cannot_rewrite_a_grow_snapshot(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    service.update_system_profile(
        {"lighting": {"brand": "Original fixture", "model": "QB-240"}}
    )
    service.start_cultivation(_start_payload())

    service.update_system_profile(
        {"lighting": {"brand": "Replacement fixture", "model": "QB-320"}}
    )
    bootstrap = service.bootstrap()

    assert bootstrap["system_profile"]["lighting"]["brand"] == "Replacement fixture"
    assert (
        bootstrap["active_cultivation"]["system_snapshot"]["lighting"]["brand"]
        == "Original fixture"
    )


def test_grow_profiles_are_independent_crud_records_and_deleted_profiles_stay_deleted(tmp_path):
    database_path = tmp_path / "growasist.db"
    service = GrowAsistService(GrowAsistStore(database_path))
    tomato = service.bootstrap()["grow_profiles"]["records"]["extended_fruiting"]
    values = json.loads(json.dumps(tomato))
    values.update({"name": "Benim RDWC profilim", "description": "Bitkiden bağımsız"})
    values["stages"]["veg"]["planned_days"] = 41

    created = service.update_grow_profile(
        {"profile_id": "my_rdwc", "values": values}
    )
    assert created["id"] == "my_rdwc"
    assert created["stages"]["veg"]["planned_days"] == 41
    assert "plant_id" not in created
    assert all("nutrient_ids" not in stage for stage in created["stages"].values())

    removed = service.remove_grow_profile({"profile_id": "extended_fruiting"})
    assert removed["id"] == "extended_fruiting"

    restarted_service = GrowAsistService(GrowAsistStore(database_path))
    restarted = restarted_service.bootstrap()["grow_profiles"]
    assert "my_rdwc" in restarted["records"]
    assert "extended_fruiting" not in restarted["records"]


def test_grow_start_selects_plant_and_profile_separately_and_freezes_both(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    created = service.start_cultivation(
        _start_payload(
            cultivation_id="independent_profile_grow",
            plant_id="tomato",
            grow_profile_id="short_leaf_cycle",
        )
    )

    assert created["identity"]["plant_id"] == "tomato"
    assert created["identity"]["grow_profile_id"] == "short_leaf_cycle"
    assert created["plant_snapshot"]["id"] == "tomato"
    assert "profile" not in created["plant_snapshot"]
    assert created["grow_profile_snapshot"]["id"] == "short_leaf_cycle"
    frozen_days = created["grow_profile_snapshot"]["stages"]["veg"]["planned_days"]

    profile = service.bootstrap()["grow_profiles"]["records"]["short_leaf_cycle"]
    profile["stages"]["veg"]["planned_days"] = frozen_days + 10
    service.update_grow_profile(
        {"profile_id": "short_leaf_cycle", "values": profile}
    )
    service.remove_grow_profile({"profile_id": "short_leaf_cycle"})

    active = service.bootstrap()["active_cultivation"]
    assert active["grow_profile_snapshot"]["stages"]["veg"]["planned_days"] == frozen_days
    assert active["identity"]["grow_profile_id"] == "short_leaf_cycle"


def test_light_setup_accepts_only_an_enrolled_light_device(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    state = service.store.load_state()
    state["device_registry"]["devices"]["shelly-light"] = {
        "id": "shelly-light", "name": "Grow light", "role": "light_dimmer"
    }
    service.store.save_state(state)

    saved = service.update_system_profile({
        "lighting": {"device_id": "shelly-light", "model": "QB-240"}
    })

    assert saved["lighting"]["device_id"] == "shelly-light"
    with pytest.raises(ValueError, match="ışık kontrolü"):
        service.update_system_profile({"lighting": {"device_id": "missing"}})


def test_setup_modules_are_visible_and_persist_without_enabling_control(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))

    bootstrap = service.bootstrap()
    assert set(("plant_catalog", "grow_profiles", "nutrient_catalog", "hardware", "assistant_settings")) <= set(bootstrap)
    assert "profiles" not in bootstrap
    assert len(bootstrap["nutrient_catalog"]["products"]) >= 367
    assert bootstrap["plant_catalog"]["records"]["cannabis"]["cultivars"]

    profile_values = deepcopy(
        bootstrap["grow_profiles"]["records"]["extended_fruiting"]
    )
    profile_values["stages"]["bloom"]["planned_days"] = 63
    profile = service.update_grow_profile(
        {"profile_id": "extended_fruiting", "values": profile_values}
    )
    plant = service.update_plant(
        {
            "plant_id": "tomato",
            "values": {
                **bootstrap["plant_catalog"]["records"]["tomato"],
                "notes": "Yerel kullanıcı notu",
            },
        }
    )
    hardware = service.update_hardware(
        {
            "i2c_bus": 1,
            "poll_interval": 45,
            "dosing_fluids": [
                {"id": "ph_up", "name": "pH+"},
                {"id": "ph_down", "name": "pH-"},
                {"id": "bloom_a", "name": "Bloom A", "category": "base"},
            ],
            "device_assignments": [
                {"address": "0x63", "driver": "atlas_ph", "name": "EZO pH"},
                {
                    "address": "0x40",
                    "driver": "waveshare_motor_hat",
                    "name": "Motor HAT",
                    "channels": [
                        {"id": "A", "fluid_id": "bloom_a", "calibration": {"seconds": 10, "volume_ml": 12, "speed": 100}},
                        {"id": "B", "fluid_id": "ph_down", "calibration": None},
                    ],
                },
            ],
        }
    )

    restarted = GrowAsistService(GrowAsistStore(service.store.database_path)).bootstrap()
    assert profile["stages"]["bloom"]["planned_days"] == 63
    assert plant["notes"] == "Yerel kullanıcı notu"
    assert hardware["poll_interval"] == 45
    assert hardware["device_assignments"][1]["channels"][0]["calibration"]["flow_ml_s"] == 1.2
    assert restarted["grow_profiles"]["records"]["extended_fruiting"]["stages"]["bloom"]["planned_days"] == 63
    assert restarted["hardware"]["dosing_fluids"][2]["id"] == "bloom_a"
    assert restarted["engine_enabled"] is False


def test_i2c_discovery_enrollment_and_removal_preserve_fluids(tmp_path, monkeypatch):
    class FakeGateway:
        def __init__(self, bus_number):
            assert bus_number == 1

        def scan(self, assignments):
            return {
                "health": {"available": True, "path": "/dev/i2c-1", "error": ""},
                "last_scan": {"finished_at": "2026-08-28T10:00:00Z", "candidate_count": 1, "online_count": 1, "warnings": []},
                "candidates": {"i2c_1_40": {
                    "id": "i2c_1_40", "address": 0x40, "address_hex": "0x40",
                    "online": True, "supported": True, "configured": False,
                    "model": "PCA9685 PWM denetleyici", "chip": "PCA9685",
                    "suggested_driver": "waveshare_motor_hat", "driver_locked": False,
                    "requires_driver_confirmation": True,
                }},
            }

    monkeypatch.setattr("growasist.service.I2CHardwareGateway", FakeGateway)
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    service.update_hardware({"dosing_fluids": [
        {"id": "ph_up", "name": "pH+"},
        {"id": "ph_down", "name": "pH-"},
        {"id": "bloom_a", "name": "Bloom A", "category": "base"},
    ]})

    discovered = service.discover_i2c({})
    enrolled = service.enroll_i2c_device({
        "candidate_id": "i2c_1_40", "name": "Dozaj kartı",
        "driver": "waveshare_motor_hat",
    })
    assert enrolled["channels"][0]["fluid_id"] == "unassigned"
    enrolled["channels"][0]["fluid_id"] = "bloom_a"
    service.update_hardware({"device_assignments": [enrolled]})
    removed = service.remove_i2c_device({"address": 0x40})
    restored = service.enroll_i2c_device({
        "candidate_id": "i2c_1_40", "name": "Dozaj kartı",
        "driver": "waveshare_motor_hat",
    })
    service.remove_i2c_device({"address": 0x40})
    bootstrap = service.bootstrap()

    assert discovered["health"]["available"] is True
    assert removed["removed"]["name"] == "Dozaj kartı"
    assert restored["channels"][0]["fluid_id"] == "bloom_a"
    assert any(item["id"] == "bloom_a" for item in bootstrap["hardware"]["dosing_fluids"])
    assert bootstrap["hardware"]["device_assignments"] == []
    assert bootstrap["i2c_registry"]["retired_assignments"][0]["address"] == 0x40


def test_pump_calibration_requires_real_run_receipt(tmp_path, monkeypatch):
    calls = []

    class FakeGateway:
        def __init__(self, bus_number):
            assert bus_number == 1

        def run_pump(self, address, channel, seconds, speed):
            calls.append((address, channel, seconds, speed))

    monkeypatch.setattr("growasist.service.I2CHardwareGateway", FakeGateway)
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    service.update_hardware({"device_assignments": [{
        "address": 0x40, "driver": "waveshare_motor_hat", "name": "Motor HAT",
        "channels": [
            {"id": "A", "fluid_id": "ph_down", "pump": {}, "calibration": None},
            {"id": "B", "fluid_id": "unassigned", "pump": {}, "calibration": None},
        ],
    }]})

    with pytest.raises(ValueError, match="güvenlik onayı"):
        service.test_pump({"address": 0x40, "channel": "A", "seconds": 1})
    tested = service.test_pump({
        "address": 0x40, "channel": "A", "seconds": 3,
        "speed": 60, "confirm": True,
    })
    run = service.start_pump_calibration({
        "address": 0x40, "channel": "A", "seconds": 10,
        "speed": 100, "confirm": True,
    })
    calibrated = service.complete_pump_calibration({
        "token": run["token"], "volume_ml": 12,
    })

    assert tested["stopped"] is True
    assert calls == [(0x40, "A", 3.0, 60), (0x40, "A", 10.0, 100)]
    assert calibrated["calibration"]["flow_ml_s"] == 1.2
    assert calibrated["pump"]["verified"] is True
    with pytest.raises(ValueError, match="bulunamadı veya süresi doldu"):
        service.complete_pump_calibration({"token": run["token"], "volume_ml": 12})


def test_official_catalog_product_is_added_once_and_keeps_details(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    catalog = service.bootstrap()["nutrient_catalog"]
    product = next(
        item for item in catalog["products"].values()
        if item["brand"] == "Advanced Nutrients" and item["name"] == "Big Bud"
    )

    first = service.add_catalog_nutrient({"catalog_id": product["id"]})
    second = service.add_catalog_nutrient({"catalog_id": product["id"]})
    fluids = service.bootstrap()["hardware"]["dosing_fluids"]
    imported = [item for item in fluids if item.get("catalog_id") == product["id"]]

    assert first["created"] is True
    assert second["created"] is False
    assert len(imported) == 1
    assert imported[0]["brand"] == "Advanced Nutrients"
    assert imported[0]["description"]
    assert imported[0]["source_url"].startswith("https://")
    assert imported[0]["official"] is True
    assert service.bootstrap()["engine_enabled"] is False


def test_catalog_program_adds_the_set_atomically_and_deduplicates(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    catalog = service.bootstrap()["nutrient_catalog"]
    program = next(
        item for item in catalog["programs"].values()
        if item["brand_id"] == "canna" and item["line"] == "CANNA AQUA"
    )

    first = service.add_nutrient_program({"program_id": program["id"], "scope": "core"})
    second = service.add_nutrient_program({"program_id": program["id"], "scope": "core"})
    local_catalog_ids = {
        item.get("catalog_id") for item in service.bootstrap()["hardware"]["dosing_fluids"]
    }

    assert len(first["added"]) == len(program["core_product_ids"])
    assert second["added"] == []
    assert len(second["existing"]) == len(program["core_product_ids"])
    assert set(program["core_product_ids"]) <= local_catalog_ids


def test_grow_start_snapshots_a_catalog_set_without_changing_inventory(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    catalog = service.bootstrap()["nutrient_catalog"]
    owned_before = service.bootstrap()["hardware"]["dosing_fluids"]
    program = next(
        item for item in catalog["programs"].values()
        if item["brand_id"] == "canna" and item["line"] == "CANNA AQUA"
    )

    cultivation = service.start_cultivation(_start_payload(
        nutrient_set_id=program["id"],
        nutrient_set_scope="core",
        nutrient_program="",
    ))
    snapshot = cultivation["nutrient_program_snapshot"]

    assert cultivation["identity"]["nutrient_program"] == program["name"]
    assert snapshot["set_id"] == program["id"]
    assert snapshot["program_id"] == program["id"]
    assert snapshot["brand"] == "CANNA"
    assert snapshot["catalog_product_ids"] == program["core_product_ids"]
    assert len(snapshot["products"]) == len(program["core_product_ids"])
    assert snapshot["dose_plan_included"] is False
    assert snapshot["catalog_version"] == catalog["catalog_version"]
    assert snapshot["stages"]["veg"]["catalog_product_ids"]
    assert snapshot["stages"]["veg"]["nutrient_ids"] == []
    assert service.bootstrap()["hardware"]["dosing_fluids"] == owned_before


def test_grow_start_rejects_a_program_for_the_wrong_environment(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    catalog = service.bootstrap()["nutrient_catalog"]
    soil_program = next(
        item for item in catalog["programs"].values()
        if item["brand_id"] == "canna" and item["line"] == "CANNA TERRA"
    )

    with pytest.raises(ValueError, match="ortamıyla uyumlu değil"):
        service.start_cultivation(_start_payload(
            nutrient_program_id=soil_program["id"],
            nutrient_program_scope="core",
        ))


def test_grow_start_snapshots_selected_nutrient_products(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    service.update_hardware({
        "dosing_fluids": [
            {"id": "ph_up", "name": "pH+", "category": "ph"},
            {"id": "ph_down", "name": "pH-", "category": "ph"},
            {"id": "bloom_a", "name": "Bloom A", "brand": "Test", "category": "base"},
            {"id": "calmag", "name": "Cal-Mag", "brand": "Test", "category": "supplement"},
        ]
    })

    cultivation = service.start_cultivation(_start_payload(
        nutrient_program="Bloom programı",
        nutrient_ids=["bloom_a", "calmag"],
    ))

    snapshot = cultivation["nutrient_program_snapshot"]
    assert snapshot["name"] == "Bloom programı"
    assert snapshot["nutrient_ids"] == ["bloom_a", "calmag"]
    assert [item["name"] for item in snapshot["products"]] == ["Bloom A", "Cal-Mag"]
    assert service.bootstrap()["engine_enabled"] is False


def test_plant_profile_and_nutrient_ledgers_have_no_cross_links(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    service.update_hardware({
        "dosing_fluids": [
            {"id": "ph_up", "name": "pH+", "category": "ph"},
            {"id": "ph_down", "name": "pH-", "category": "ph"},
            {"id": "tomato_a", "name": "Tomato A", "category": "base"},
            {"id": "cannabis_a", "name": "Cannabis A", "category": "base"},
        ]
    })
    bootstrap = service.bootstrap()
    plants = bootstrap["plant_catalog"]["records"]
    profiles = bootstrap["grow_profiles"]["records"]
    nutrients = bootstrap["nutrient_catalog"]

    assert all("profile" not in plant for plant in plants.values())
    assert all("plant_id" not in profile for profile in profiles.values())
    assert all("nutrient_ids" not in profile for profile in profiles.values())
    assert all(
        "nutrient_ids" not in stage
        for profile in profiles.values()
        for stage in profile["stages"].values()
    )
    assert all("plant_id" not in product for product in nutrients["products"].values())
    assert all("grow_profile_id" not in program for program in nutrients["programs"].values())


def test_cannabis_requires_growth_type_when_no_catalog_cultivar_is_selected(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))

    with pytest.raises(ValueError, match="Photoperiod veya Autoflower"):
        service.start_cultivation(
            _start_payload(
                cultivation_id="cannabis_grow",
                plant_id="cannabis",
                grow_profile_id="photoperiod_18_12",
            )
        )


def test_service_rejects_future_journal_dates(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    service.start_cultivation(_start_payload())

    with pytest.raises(ValueError, match="gelecekte olamaz"):
        service.append_journal_event(
            {
                "type": "user_note",
                "local_date": (date.today() + timedelta(days=1)).isoformat(),
                "note": "Future",
            }
        )


@pytest.fixture
def standalone_http(tmp_path):
    store = GrowAsistStore(tmp_path / "growasist.db")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), build_handler(store, "test-secret")
    )
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(address, method, path, *, token=None, payload=None):
    connection = HTTPConnection(*address, timeout=2)
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    content = response.read()
    connection.close()
    return response.status, response.headers, content


def test_web_shell_is_public_but_grow_data_requires_token(standalone_http):
    status, headers, body = _request(standalone_http, "GET", "/")
    assert status == 200
    assert b"GrowAsist" in body
    assert headers["X-Frame-Options"] == "DENY"

    status, _, _ = _request(standalone_http, "GET", "/api/v1/bootstrap")
    assert status == 401

    status, _, body = _request(
        standalone_http,
        "GET",
        "/api/v1/bootstrap",
        token="test-secret",
    )
    assert status == 200
    assert json.loads(body)["mode"] == "standalone"


def test_http_api_starts_grow_and_appends_immutable_event(standalone_http):
    status, _, _ = _request(
        standalone_http,
        "POST",
        "/api/v1/cultivations/start",
        token="test-secret",
        payload=_start_payload(),
    )
    assert status == 200

    status, _, _ = _request(
        standalone_http,
        "POST",
        "/api/v1/journal/events",
        token="test-secret",
        payload={
            "event_id": "api_note",
            "type": "user_note",
            "local_date": date.today().isoformat(),
            "note": "API üzerinden kalıcı not",
        },
    )
    assert status == 200

    _, _, body = _request(
        standalone_http,
        "GET",
        "/api/v1/journal/export",
        token="test-secret",
    )
    export = json.loads(body)
    assert any(event["id"] == "api_note" for event in export["events"])
    assert export["checksum"]


def test_http_api_saves_setup_modules(standalone_http):
    _, _, body = _request(
        standalone_http, "GET", "/api/v1/bootstrap", token="test-secret"
    )
    bootstrap = json.loads(body)
    values = bootstrap["grow_profiles"]["records"]["extended_fruiting"]
    values["stages"]["veg"]["planned_days"] = 31
    for path, payload in (
        ("/api/v1/grow-profiles", {"profile_id": "extended_fruiting", "values": values}),
        ("/api/v1/hardware", {"poll_interval": 60}),
    ):
        status, _, body = _request(
            standalone_http,
            "POST",
            path,
            token="test-secret",
            payload=payload,
        )
        assert status == 200, body

    _, _, body = _request(
        standalone_http,
        "GET",
        "/api/v1/bootstrap",
        token="test-secret",
    )
    bootstrap = json.loads(body)
    assert bootstrap["grow_profiles"]["records"]["extended_fruiting"]["stages"]["veg"]["planned_days"] == 31
    assert bootstrap["hardware"]["poll_interval"] == 60


def test_http_api_creates_and_removes_an_independent_grow_profile(standalone_http):
    _, _, body = _request(
        standalone_http, "GET", "/api/v1/bootstrap", token="test-secret"
    )
    bootstrap = json.loads(body)
    values = bootstrap["grow_profiles"]["records"]["short_leaf_cycle"]
    values["name"] = "API profili"

    status, _, body = _request(
        standalone_http,
        "POST",
        "/api/v1/grow-profiles",
        token="test-secret",
        payload={"profile_id": "api_profile", "values": values},
    )
    assert status == 200, body
    assert json.loads(body)["result"]["name"] == "API profili"

    status, _, body = _request(
        standalone_http,
        "POST",
        "/api/v1/grow-profiles/remove",
        token="test-secret",
        payload={"profile_id": "api_profile"},
    )
    assert status == 200, body
    assert json.loads(body)["result"]["id"] == "api_profile"


def test_http_api_adds_an_official_nutrient_catalog_product(standalone_http):
    _, _, body = _request(
        standalone_http, "GET", "/api/v1/bootstrap", token="test-secret"
    )
    bootstrap = json.loads(body)
    product_id = bootstrap["nutrient_catalog"]["product_order"][0]

    status, _, body = _request(
        standalone_http,
        "POST",
        "/api/v1/nutrients/catalog/add",
        token="test-secret",
        payload={"catalog_id": product_id},
    )

    assert status == 200, body
    assert json.loads(body)["result"]["created"] is True
