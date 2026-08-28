"""Standalone I2C gateway discovery and motor safety tests."""

from __future__ import annotations

from dataclasses import dataclass

from growasist.hardware_gateway import I2CHardwareGateway


@dataclass
class _AtlasDevice:
    address: int
    device_type: str
    firmware: str


@dataclass
class _Hat:
    address: int
    mode1: int
    prescale: int


class _Atlas:
    closed = False

    def __init__(self, _bus_number):
        pass

    def discover(self, addresses):
        assert 0x63 in addresses
        return [_AtlasDevice(0x63, "pH", "2.15")]

    def close(self):
        self.closed = True


class _Inventory:
    closed = False

    def __init__(self, _bus_number):
        pass

    def discover(self, addresses):
        addresses = list(addresses)
        return [_Hat(0x40, 1, 121)] if 0x40 in addresses else []

    def close(self):
        self.closed = True


class _Controller:
    calls = []

    def __init__(self, *, bus_number, address):
        self.bus_number = bus_number
        self.address = address

    def timed_run(self, channel, seconds, speed):
        self.calls.append((self.address, channel, seconds, speed))

    def close(self):
        self.calls.append((self.address, "closed"))


def test_scan_merges_physical_identity_with_configuration(tmp_path):
    path = tmp_path / "i2c-1"
    path.touch()
    gateway = I2CHardwareGateway(
        1,
        device_path=path,
        atlas_factory=_Atlas,
        motor_inventory_factory=_Inventory,
    )

    result = gateway.scan([
        {"address": 0x63, "driver": "atlas_ph", "name": "Reservoir pH"},
        {"address": 0x41, "driver": "waveshare_motor_hat", "name": "Missing HAT"},
    ])

    ph = result["candidates"]["i2c_1_63"]
    hat = result["candidates"]["i2c_1_40"]
    missing = result["candidates"]["i2c_1_41"]
    assert result["health"]["available"] is True
    assert ph["identity_verified"] is True
    assert ph["configured"] is True
    assert ph["driver"] == "atlas_ph"
    assert hat["requires_driver_confirmation"] is True
    assert hat["identity_verified"] is False
    assert hat["configured"] is False
    assert missing["online"] is False
    assert missing["configured"] is True


def test_scan_reports_missing_kernel_device_without_opening_drivers(tmp_path):
    gateway = I2CHardwareGateway(
        1,
        device_path=tmp_path / "missing",
        atlas_factory=lambda _bus: (_ for _ in ()).throw(AssertionError()),
        motor_inventory_factory=lambda _bus: (_ for _ in ()).throw(AssertionError()),
    )

    result = gateway.scan([])

    assert result["health"]["available"] is False
    assert result["last_scan"]["online_count"] == 0


def test_motor_run_freshly_verifies_then_closes_controller(tmp_path):
    _Controller.calls.clear()
    path = tmp_path / "i2c-1"
    path.touch()
    gateway = I2CHardwareGateway(
        1,
        device_path=path,
        atlas_factory=_Atlas,
        motor_inventory_factory=_Inventory,
        motor_controller_factory=_Controller,
    )

    gateway.run_pump(0x40, "A", 1.5, 60)

    assert _Controller.calls == [(0x40, "A", 1.5, 60), (0x40, "closed")]
