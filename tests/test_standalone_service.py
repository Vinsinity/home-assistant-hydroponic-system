"""Standalone service and authenticated web API tests."""

from __future__ import annotations

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
        "plant_profile_id": "tomato",
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
            plant_profile_id="",
            plant_species="Pak choi",
        )
    )
    restarted = service.bootstrap()

    custom_id = grow["identity"]["plant_profile_id"]
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


def test_cannabis_requires_growth_type_when_no_catalog_cultivar_is_selected(tmp_path):
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))

    with pytest.raises(ValueError, match="Photoperiod veya Autoflower"):
        service.start_cultivation(
            _start_payload(
                cultivation_id="cannabis_grow",
                plant_profile_id="cannabis",
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
