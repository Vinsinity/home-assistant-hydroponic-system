"""Read-only LAN discovery and enrollment tests."""

from __future__ import annotations

import json
import ipaddress
import struct

import pytest

from growasist.discovery import (
    NetworkDiscovery,
    OuiRegistry,
    _candidate,
    _dns_name,
    _infer_shelly_capabilities,
    _parse_mdns_packet,
    _shelly_candidate,
    _tplink_candidate,
    _tuya_packet_kind,
    _xml_values,
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


def test_ieee_oui_registry_and_upnp_identity_are_reduced_to_display_fields(tmp_path):
    registry_file = tmp_path / "oui.csv"
    registry_file.write_text(
        "Registry,Assignment,Organization Name,Organization Address\n"
        "MA-L,AABBCC,Example Device Company,Secret office\n",
        encoding="utf-8",
    )
    registry = OuiRegistry(paths=(registry_file,))
    assert registry.lookup("AA:BB:CC:12:34:56") == "Example Device Company"
    assert registry.lookup("02:00:00:00:00:01") == ""

    identity = _xml_values(b"""<?xml version='1.0'?>
        <root xmlns='urn:schemas-upnp-org:device-1-0'><device>
        <friendlyName>Grow room plug</friendlyName><manufacturer>Example</manufacturer>
        <modelName>P100</modelName><serialNumber>must-not-leak</serialNumber>
        </device></root>""")
    assert identity == {"name": "Grow room plug", "manufacturer": "Example", "model": "P100"}


def test_tuya_frame_recognition_does_not_attempt_to_decrypt_payloads():
    assert _tuya_packet_kind(b"\x00\x00\x55\xaa" + b"encrypted") == "tuya_55aa"
    assert _tuya_packet_kind(b"\x00\x00\x66\x99" + b"encrypted") == "tuya_6699"
    assert _tuya_packet_kind(b"not-tuya") == ""


def test_discovery_merge_keeps_strong_identity_and_all_evidence():
    target = {}
    NetworkDiscovery._merge(target, _candidate(
        "10.1.1.50", mac="AA:BB:CC:DD:EE:FF", evidence=["Ağ komşusu"], methods=["arp_neighbor"]
    ))
    NetworkDiscovery._merge(target, _candidate(
        "10.1.1.50", vendor="Shelly", model="H&T Gen3", mac="AA:BB:CC:DD:EE:FF",
        protocol="shelly_rpc", confidence=98, evidence=["Shelly kimlik yanıtı"],
        methods=["shelly_http"], supported=True,
    ))
    merged = next(iter(target.values()))
    assert merged["vendor"] == "Shelly"
    assert merged["identity_confidence"] == 98
    assert merged["discovery_methods"] == ["arp_neighbor", "shelly_http"]
    assert merged["evidence"] == ["Ağ komşusu", "Shelly kimlik yanıtı"]


def test_subnet_inventory_includes_neighbors_without_open_tcp_ports(monkeypatch):
    discovery = NetworkDiscovery.__new__(NetworkDiscovery)
    discovery.local_ip = "10.1.1.1"
    discovery.network = ipaddress.ip_network("10.1.1.0/30")
    discovery.oui = OuiRegistry(paths=())
    monkeypatch.setattr(NetworkDiscovery, "_open_ports", staticmethod(lambda host: (host, [])))
    monkeypatch.setattr(NetworkDiscovery, "_arp_table", staticmethod(lambda: {"10.1.1.2": "A8:29:48:12:34:56"}))

    candidates = discovery._scan_subnet()

    assert len(candidates) == 1
    assert candidates[0]["host"] == "10.1.1.2"
    assert candidates[0]["manufacturer"] == "TP-Link Technologies"
    assert candidates[0]["discovery_methods"] == ["arp_neighbor"]


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


def test_unknown_device_requires_confirmation_and_identity_survives_rescan(tmp_path, monkeypatch):
    class FakeDiscovery:
        def __init__(self, *, timeout):
            pass

        def scan(self):
            return {
                "started_at": "2026-08-28T10:00:00+00:00",
                "finished_at": "2026-08-28T10:00:01+00:00",
                "network": "10.1.1.0/24",
                "local_ip": "10.1.1.130",
                "candidate_count": 1,
                "observed_host_count": 1,
                "recognized_count": 0,
                "grow_candidate_count": 0,
                "protocol_counts": {"arp_neighbor": 1},
                "duration_ms": 1000,
                "warnings": [],
                "candidates": [_candidate(
                    "10.1.1.83", mac="70:68:71:4B:34:4E", name="FN-LINK Technology",
                    manufacturer="FN-LINK Technology", confidence=48,
                    evidence=["IEEE üreticisi: FN-LINK Technology"], methods=["arp_neighbor"],
                )],
            }

    monkeypatch.setattr("growasist.service.NetworkDiscovery", FakeDiscovery)
    service = GrowAsistService(GrowAsistStore(tmp_path / "growasist.db"))
    candidate_id = next(iter(service.discover_network({"timeout": 3})["candidates"]))

    with pytest.raises(ValueError, match="marka/model"):
        service.enroll_network_device({"candidate_id": candidate_id, "role": "humidifier"})

    enrolled = service.enroll_network_device({
        "candidate_id": candidate_id,
        "name": "Ana nemlendirici",
        "vendor": "Dreo",
        "model": "Smart Humidifier",
        "role": "humidifier",
        "confirm_identity": True,
    })
    assert enrolled["vendor"] == "Dreo"
    assert enrolled["identity_source"] == "user_confirmed"
    assert enrolled["identity_confidence"] == 100

    service.remove_network_device({"candidate_id": candidate_id})
    rescanned = service.discover_network({"timeout": 3})
    remembered = rescanned["candidates"][candidate_id]
    assert remembered["vendor"] == "Dreo"
    assert remembered["name"] == "Ana nemlendirici"
    assert remembered["identity_source"] == "user_confirmed"
