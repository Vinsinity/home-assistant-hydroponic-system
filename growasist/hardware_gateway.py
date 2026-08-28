"""Standalone Raspberry Pi hardware discovery and guarded pump operations."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from custom_components.hydroponic_system.hardware.atlas_ezo import (
    DEFAULT_ADDRESSES,
    AtlasEzoBus,
)
from custom_components.hydroponic_system.hardware.motor_hat import (
    MotorHatInventory,
    WaveshareMotorHatController,
)


_ATLAS_DRIVERS = {
    "DO": "atlas_do",
    "PH": "atlas_ph",
    "EC": "atlas_ec",
    "RTD": "atlas_rtd",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class I2CHardwareGateway:
    """Own real I2C discovery and bounded motor actions for the appliance."""

    def __init__(
        self,
        bus_number: int = 1,
        *,
        device_path: str | Path | None = None,
        atlas_factory: Callable[[int], Any] = AtlasEzoBus,
        motor_inventory_factory: Callable[[int], Any] = MotorHatInventory,
        motor_controller_factory: Callable[..., Any] = WaveshareMotorHatController,
    ) -> None:
        self.bus_number = int(bus_number)
        self.device_path = Path(device_path or f"/dev/i2c-{self.bus_number}")
        self._atlas_factory = atlas_factory
        self._motor_inventory_factory = motor_inventory_factory
        self._motor_controller_factory = motor_controller_factory

    @staticmethod
    def _candidate_id(bus_number: int, address: int) -> str:
        return f"i2c_{bus_number}_{address:02x}"

    def _base_candidate(self, address: int) -> dict[str, Any]:
        return {
            "id": self._candidate_id(self.bus_number, address),
            "transport": "i2c",
            "bus": self.bus_number,
            "path": str(self.device_path),
            "address": address,
            "address_hex": f"0x{address:02X}",
            "online": True,
            "supported": True,
            "last_seen": _utc_now(),
            "enrolled": False,
            "configured": False,
            "status": "detected",
        }

    def scan(self, assignments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Read identities/registers only; never write to an attached device."""
        configured = {
            int(item["address"]): item
            for item in assignments or []
            if isinstance(item, dict) and isinstance(item.get("address"), int)
        }
        health = {
            "available": self.device_path.exists(),
            "path": str(self.device_path),
            "error": "" if self.device_path.exists() else f"{self.device_path} bulunamadı",
        }
        candidates: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []

        if self.device_path.exists():
            atlas_addresses = set(DEFAULT_ADDRESSES)
            atlas_addresses.update(
                address
                for address, item in configured.items()
                if str(item.get("driver", "")).startswith("atlas_")
            )
            atlas = None
            try:
                atlas = self._atlas_factory(self.bus_number)
                for device in atlas.discover(sorted(atlas_addresses)):
                    driver = _ATLAS_DRIVERS.get(str(device.device_type).upper())
                    if not driver:
                        continue
                    candidate = self._base_candidate(device.address)
                    candidate.update({
                        "chip": "Atlas Scientific EZO",
                        "model": f"EZO {str(device.device_type).upper()}",
                        "firmware": device.firmware or "",
                        "suggested_driver": driver,
                        "driver_locked": True,
                        "identity_verified": True,
                        "requires_driver_confirmation": False,
                    })
                    candidates[candidate["id"]] = candidate
            except OSError as error:
                health["available"] = False
                health["error"] = str(error)
                warnings.append(f"Atlas taraması: {error}")
            finally:
                if atlas is not None:
                    atlas.close()

            inventory = None
            try:
                inventory = self._motor_inventory_factory(self.bus_number)
                for hat in inventory.discover(range(0x40, 0x60)):
                    candidate = self._base_candidate(hat.address)
                    candidate.update({
                        "chip": "PCA9685 uyumlu yanıt",
                        "model": "PWM denetleyici adayı",
                        "firmware": "",
                        "mode1": hat.mode1,
                        "prescale": hat.prescale,
                        "suggested_driver": "waveshare_motor_hat",
                        "driver_locked": False,
                        "identity_verified": False,
                        "requires_driver_confirmation": True,
                    })
                    candidates[candidate["id"]] = candidate
            except OSError as error:
                health["available"] = False
                health["error"] = str(error)
                warnings.append(f"Motor kartı taraması: {error}")
            finally:
                if inventory is not None:
                    inventory.close()

        for address, assignment in configured.items():
            candidate_id = self._candidate_id(self.bus_number, address)
            candidate = candidates.get(candidate_id)
            if candidate is None:
                candidate = self._base_candidate(address)
                candidate.update({
                    "chip": "Yapılandırılmış cihaz",
                    "model": str(assignment.get("name") or f"I²C 0x{address:02X}"),
                    "firmware": "",
                    "suggested_driver": str(assignment.get("driver") or ""),
                    "driver_locked": str(assignment.get("driver", "")).startswith("atlas_"),
                    "identity_verified": False,
                    "requires_driver_confirmation": str(assignment.get("driver")) in {
                        "waveshare_motor_hat", "pca9685_generic",
                    },
                    "online": False,
                    "last_seen": "",
                    "status": "offline",
                })
                candidates[candidate_id] = candidate
            candidate.update({
                "configured": True,
                "enrolled": True,
                "driver": str(assignment.get("driver") or ""),
                "name": str(assignment.get("name") or candidate.get("model") or ""),
                "status": "online" if candidate.get("online") else "offline",
            })

        return {
            "health": health,
            "candidates": candidates,
            "last_scan": {
                "finished_at": _utc_now(),
                "candidate_count": len(candidates),
                "online_count": sum(bool(item.get("online")) for item in candidates.values()),
                "warnings": warnings,
            },
        }

    def verify_motor_hat(self, address: int) -> dict[str, int]:
        """Fresh read-only register check immediately before a motor action."""
        inventory = self._motor_inventory_factory(self.bus_number)
        try:
            devices = inventory.discover([int(address)])
        finally:
            inventory.close()
        if not devices:
            raise ValueError(f"0x{int(address):02X} adresindeki motor kartı yanıt vermiyor")
        return {"mode1": devices[0].mode1, "prescale": devices[0].prescale}

    def run_pump(self, address: int, channel: str, seconds: float, speed: int) -> None:
        """Verify the controller, run once, and rely on the driver's guaranteed stop."""
        self.verify_motor_hat(address)
        controller = self._motor_controller_factory(
            bus_number=self.bus_number,
            address=int(address),
        )
        try:
            controller.timed_run(str(channel).upper(), float(seconds), int(speed))
        finally:
            controller.close()
