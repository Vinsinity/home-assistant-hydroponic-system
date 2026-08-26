"""Home Assistant coordinator for native Atlas I2C probes."""

from __future__ import annotations

from datetime import timedelta
import asyncio
import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..const import DOMAIN
from .atlas_ezo import DEFAULT_ADDRESSES, AtlasDevice, AtlasEzoBus
from .motor_hat import MotorHatInventory, WaveshareMotorHatController

_LOGGER = logging.getLogger(__name__)


class AtlasI2CCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Poll all discovered Atlas circuits sequentially on one shared bus."""

    def __init__(self, hass: HomeAssistant, bus_number: int = 1, hardware=None) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN} Atlas I2C",
            update_interval=timedelta(
                seconds=max(10, min(300, int((hardware or {}).get("poll_interval", 30))))
            ),
        )
        self.bus_number = bus_number
        self.device_path = Path(f"/dev/i2c-{bus_number}")
        self.devices: list[AtlasDevice] = []
        self.hardware = hardware or {}
        self.assignments = {
            int(item["address"]): item
            for item in self.hardware.get("device_assignments", [])
            if "address" in item
        }
        self._bus_lock = asyncio.Lock()
        self.diagnostic: dict[str, object] = {
            "available": False,
            "path": str(self.device_path),
            "error": None,
            "devices": [],
            "motor_hats": [],
            "discovered_devices": [],
        }

    async def async_initialize(self) -> bool:
        """Discover hardware without failing the rest of the integration."""
        if not self.device_path.exists():
            self.diagnostic["error"] = "I2C device path is not available"
            return False
        try:
            self.devices, motor_hats, discovered = await self.hass.async_add_executor_job(self._discover)
        except (OSError, ImportError) as err:
            self.diagnostic["error"] = f"{type(err).__name__}: {err}"
            return False
        self._apply_discovery(self.devices, motor_hats, discovered)
        return True

    def _apply_discovery(self, devices, motor_hats, discovered) -> None:
        """Publish one discovery result without replacing the coordinator."""
        self.devices = devices
        self.diagnostic.update({
                "available": True,
                "error": None,
                "devices": [
                    {
                        "address": f"0x{device.address:02x}",
                        "type": device.device_type,
                        "firmware": device.firmware,
                    }
                    for device in self.devices
                ],
                "motor_hats": motor_hats,
                "discovered_devices": discovered,
            })

    async def async_reconfigure(self, hardware: dict) -> None:
        """Apply hardware assignments live and refresh measurements."""
        self.hardware = hardware
        self.assignments = {
            int(item["address"]): item
            for item in hardware.get("device_assignments", [])
            if "address" in item
        }
        self.update_interval = timedelta(
            seconds=max(10, min(300, int(hardware.get("poll_interval", 30))))
        )
        async with self._bus_lock:
            devices, motor_hats, discovered = await self.hass.async_add_executor_job(
                self._discover
            )
            self._apply_discovery(devices, motor_hats, discovered)
            data = await self.hass.async_add_executor_job(self._read_all)
        self.async_set_updated_data(data)

    def _discover(self):
        atlas_drivers = {"atlas_do", "atlas_ph", "atlas_ec", "atlas_rtd"}
        atlas_assignments = {
            address: item for address, item in self.assignments.items()
            if item.get("driver") in atlas_drivers
        }
        addresses = set(DEFAULT_ADDRESSES)
        addresses.update(atlas_assignments)
        bus = AtlasEzoBus(self.bus_number)
        try:
            atlas_candidates = bus.discover(sorted(addresses))
        finally:
            bus.close()
        devices = [
            device for device in atlas_candidates if device.address in atlas_assignments
        ]
        inventory = MotorHatInventory(self.bus_number)
        try:
            hats = []
            for hat in inventory.discover(range(0x40, 0x60)):
                assignment = self.assignments.get(hat.address, {})
                hats.append({
                    "address": f"0x{hat.address:02x}",
                    "mode1": f"0x{hat.mode1:02x}",
                    "prescale": f"0x{hat.prescale:02x}",
                    "chip": "PCA9685",
                    "driver": assignment.get("driver"),
                    "name": assignment.get("name"),
                    "model": "Waveshare Motor Driver HAT" if assignment.get("driver") == "waveshare_motor_hat" else None,
                    "channels": hat.channels if assignment.get("driver") == "waveshare_motor_hat" else [],
                    "outputs_enabled": False,
                })
        finally:
            inventory.close()
        discovered = [
            {
                "address": f"0x{device.address:02x}",
                "chip": f"Atlas EZO {device.device_type}",
                "suggested_driver": f"atlas_{device.device_type.lower()}",
                "firmware": device.firmware,
            }
            for device in atlas_candidates
        ] + [
            {
                "address": hat["address"],
                "chip": "PCA9685",
                "suggested_driver": "waveshare_motor_hat",
                "firmware": None,
            }
            for hat in hats
        ]
        return devices, hats, discovered

    def _read_all(self) -> dict[str, dict]:
        bus = AtlasEzoBus(self.bus_number)
        result: dict[str, dict] = {}
        try:
            for device in self.devices:
                values = bus.read_measurement(device)
                result[device.key] = {
                    "address": device.address,
                    "device_type": device.device_type,
                    "firmware": device.firmware,
                    "values": values,
                }
        finally:
            bus.close()
        return result

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            async with self._bus_lock:
                return await self.hass.async_add_executor_job(self._read_all)
        except (OSError, ValueError, RuntimeError) as err:
            raise UpdateFailed(f"Atlas I2C read failed: {err}") from err

    def _device_at(self, address: int) -> AtlasDevice:
        device = next((item for item in self.devices if item.address == address), None)
        if device is None:
            raise ValueError(f"No Atlas circuit discovered at 0x{address:02x}")
        return device

    async def async_calibration_status(self, address: int) -> str:
        """Read calibration status while serializing access to the bus."""
        device = self._device_at(address)
        async with self._bus_lock:
            return await self.hass.async_add_executor_job(
                self._calibration_status, device
            )

    def _calibration_status(self, device: AtlasDevice) -> str:
        bus = AtlasEzoBus(self.bus_number)
        try:
            return bus.calibration_status(device)
        finally:
            bus.close()

    async def async_calibrate(self, address: int, operation: str, value=None) -> str:
        """Execute one validated calibration while polling is locked."""
        device = self._device_at(address)
        async with self._bus_lock:
            result = await self.hass.async_add_executor_job(
                self._calibrate, device, operation, value
            )
        await self.async_request_refresh()
        return result

    def _calibrate(self, device: AtlasDevice, operation: str, value=None) -> str:
        bus = AtlasEzoBus(self.bus_number)
        try:
            return bus.calibrate(device, operation, value)
        finally:
            bus.close()

    async def async_device_command(self, address: int, command: str) -> str:
        """Run a confirmed management command while polling is locked."""
        device = self._device_at(address)
        async with self._bus_lock:
            return await self.hass.async_add_executor_job(
                self._device_command, device, command
            )

    def _device_command(self, device: AtlasDevice, command: str) -> str:
        bus = AtlasEzoBus(self.bus_number)
        try:
            return bus.device_command(device, command)
        finally:
            bus.close()

    async def async_change_address(self, address: int, new_address: int) -> None:
        """Change the hardware address while preventing concurrent polling."""
        device = self._device_at(address)
        async with self._bus_lock:
            await self.hass.async_add_executor_job(
                self._change_address, device, new_address
            )

    def _change_address(self, device: AtlasDevice, new_address: int) -> None:
        bus = AtlasEzoBus(self.bus_number)
        try:
            bus.change_address(device, new_address)
        finally:
            bus.close()

    async def async_motor_test(
        self, address: int, channel: str, seconds: float, speed: int
    ) -> None:
        """Run one explicitly confirmed, bounded Waveshare pump test."""
        assignment = self.assignments.get(address)
        if not assignment or assignment.get("driver") != "waveshare_motor_hat":
            raise ValueError(f"No Waveshare Motor Driver HAT assigned at 0x{address:02X}")
        async with self._bus_lock:
            await self.hass.async_add_executor_job(
                self._motor_test, address, channel, seconds, speed
            )

    def _motor_test(
        self, address: int, channel: str, seconds: float, speed: int
    ) -> None:
        controller = WaveshareMotorHatController(self.bus_number, address)
        try:
            controller.timed_run(channel, seconds, speed)
        finally:
            controller.close()
