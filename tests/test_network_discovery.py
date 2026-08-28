"""Read-only LAN discovery and enrollment tests."""

from __future__ import annotations

import json
import struct

from growasist.discovery import (
    _dns_name,
    _infer_shelly_capabilities,
    _parse_mdns_packet,
    _shelly_candidate,
    _tplink_candidate,
    _xor_decrypt,
    _xor_encrypt,
)
from growasist.service import GrowAsistService
from growasist.storage import GrowAsistStore


def _dns_record(name: str, record_type: int, value: bytes) -> bytes:
    return _dns_name(name) + struct.pack(">HHIH", record_type, 1, 120, len(value)) + value


def test_mdns_parser_resolves_shelly_dns_sd_records():
    instance = "shellyhtg3-aabbcc._shelly._tcp.local"
    target = "shellyhtg3-aabbcc.local"
    packet = struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 3)
    packet += _dns_record("_shelly._tcp.local", 12, _dns_name(instance))
    packet += _dns_record(instance, 33, struct.pack(">HHH", 0, 0, 80) + _dns_name(target))
    packet += _dns_record(instance, 16, bytes([8]) + b"gen=Gen3")
    packet += _dns_record(target, 1, bytes((10, 1, 1, 42)))

    records = _parse_mdns_packet(packet)

    assert records["ptr"][0]["target"].startswith("shellyhtg3")
    assert records["srv"][0] == {
        "name": f"{instance}.",
        "target": f"{target}.",
        "port": 80,
    }
    assert records["txt"][0]["values"] == {"gen": "Gen3"}
    assert records["a"][0]["host"] == "10.1.1.42"


def test_vendor_discovery_payloads_are_reduced_to_safe_candidates():
    payload = json.dumps({"system": {"get_sysinfo": {"model": "P100", "alias": "Grow plug", "mac": "AA-BB-CC-DD-EE-FF"}}}).encode()
    assert _xor_decrypt(_xor_encrypt(payload)) == payload

    tapo = _tplink_candidate("10.1.1.50", json.loads(payload), port=9999)
    shelly = _shelly_candidate(
        "10.1.1.51",
        {"id": "shellyhtg3-aabbcc", "model": "S3SN-0U12A", "app": "HT", "mac": "AABBCCDDEEFF", "gen": 3},
    )

    assert tapo["model"] == "P100"
    assert tapo["suggested_role"] == "light_power"
    assert tapo["mac"] == "AA:BB:CC:DD:EE:FF"
    assert shelly["capabilities"] == ["temperature", "humidity"]
    assert shelly["suggested_role"] == "environment_sensor"
    assert "device_id" not in tapo
    assert "owner" not in tapo

    mesh_router = _tplink_candidate("10.1.1.52", {"result": {"device_model": "M4R"}}, port=20002)
    assert mesh_router["supported"] is False
    assert mesh_router["suggested_role"] == "unassigned"


def test_shelly_capability_inference_keeps_dimmer_and_sensor_roles_separate():
    assert _infer_shelly_capabilities("Shelly 0-10V Dimmer", "dimmer")[1] == "light_dimmer"
    assert _infer_shelly_capabilities("Shelly H&T Gen3", "HT")[1] == "environment_sensor"


def test_discovery_candidates_require_explicit_enrollment(tmp_path, monkeypatch):
    class FakeDiscovery:
        def __init__(self, *, timeout):
            assert timeout == 3

        def scan(self):
            return {
                "started_at": "2026-08-27T20:00:00+00:00",
                "finished_at": "2026-08-27T20:00:01+00:00",
                "network": "10.1.1.0/24",
                "local_ip": "10.1.1.130",
                "candidate_count": 1,
                "warnings": [],
                "candidates": [{
                    "id": "shelly_aabbccddeeff",
                    "vendor": "Shelly",
                    "name": "Grow dimmer",
                    "model": "Shelly 0-10V Dimmer",
                    "host": "10.1.1.50",
                    "port": 80,
                    "mac": "AA:BB:CC:DD:EE:FF",
                    "protocol": "shelly_rpc",
                    "capabilities": ["switch", "light", "dimmer"],
                    "suggested_role": "light_dimmer",
                    "supported": True,
                    "requires_auth": False,
                    "source": "shelly_mdns_http",
                    "last_seen": "2026-08-27T20:00:01+00:00",
                }],
            }

    monkeypatch.setattr("growasist.service.NetworkDiscovery", FakeDiscovery)
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))

    scanned = service.discover_network({"timeout": 3})
    assert "shelly_aabbccddeeff" in scanned["candidates"]
    assert scanned["devices"] == {}
    assert service.bootstrap()["engine_enabled"] is False

    enrolled = service.enroll_network_device({
        "candidate_id": "shelly_aabbccddeeff",
        "name": "Ana ışık dimmeri",
        "role": "light_dimmer",
    })
    registry = service.bootstrap()["device_registry"]

    assert enrolled["status"] == "enrolled"
    assert enrolled["role"] == "light_dimmer"
    assert enrolled["verified"] is False
    assert enrolled["connection_status"] == "adapter_pending"
    assert "shelly_aabbccddeeff" in registry["devices"]
    assert "shelly_aabbccddeeff" not in registry["candidates"]
    assert service.bootstrap()["engine_enabled"] is False

    removed = service.remove_network_device({
        "candidate_id": "shelly_aabbccddeeff",
    })
    assert "shelly_aabbccddeeff" not in removed["devices"]
    assert "shelly_aabbccddeeff" in removed["candidates"]
    assert removed["retired_devices"][0]["role"] == "light_dimmer"
