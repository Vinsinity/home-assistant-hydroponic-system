"""Small, testable Atlas Scientific EZO I2C driver.

Discovery remains read-only. Mutating management commands are exposed only through
explicitly confirmed, validated Home Assistant workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Protocol


DEFAULT_ADDRESSES = {
    0x61: "DO",
    0x63: "pH",
    0x64: "EC",
    0x66: "RTD",
}

STATUS_SUCCESS = 1
STATUS_SYNTAX_ERROR = 2
STATUS_NOT_READY = 254
STATUS_NO_DATA = 255


class AtlasProtocolError(RuntimeError):
    """An EZO circuit returned an invalid or unsuccessful response."""


class AtlasTransport(Protocol):
    """Transport boundary used by real I2C and unit tests."""

    def write(self, address: int, payload: bytes) -> None: ...

    def read(self, address: int, length: int) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AtlasDevice:
    """A discovered EZO circuit."""

    address: int
    device_type: str
    firmware: str | None = None

    @property
    def key(self) -> str:
        return f"{self.device_type.lower()}_{self.address:02x}"


class SmbusTransport:
    """Linux I2C transport backed by smbus2."""

    def __init__(self, bus_number: int) -> None:
        try:
            from smbus2 import SMBus, i2c_msg  # Imported only on supported hosts.
        except ImportError:
            from .linux_i2c import LinuxI2CBus

            self._bus = LinuxI2CBus(bus_number)
            self._message = None
        else:
            self._bus = SMBus(bus_number)
            self._message = i2c_msg

    def write(self, address: int, payload: bytes) -> None:
        if self._message is None:
            self._bus.write(address, payload)
        else:
            self._bus.i2c_rdwr(self._message.write(address, payload))

    def read(self, address: int, length: int) -> bytes:
        if self._message is None:
            return self._bus.read(address, length)
        message = self._message.read(address, length)
        self._bus.i2c_rdwr(message)
        return bytes(message)

    def close(self) -> None:
        self._bus.close()


class AtlasEzoBus:
    """Discover and poll Atlas EZO circuits on one I2C bus."""

    def __init__(
        self,
        bus_number: int = 1,
        *,
        transport: AtlasTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport or SmbusTransport(bus_number)
        self._sleep = sleep

    def close(self) -> None:
        self._transport.close()

    def command(
        self,
        address: int,
        command: str,
        *,
        processing_time: float = 0.9,
        response_length: int = 32,
    ) -> str:
        """Send one ASCII EZO command and return its ASCII response."""
        self._transport.write(address, command.encode("ascii"))
        self._sleep(processing_time)

        for attempt in range(4):
            raw = self._transport.read(address, response_length)
            if not raw:
                raise AtlasProtocolError(f"0x{address:02x}: empty response")
            status = raw[0]
            if status == STATUS_NOT_READY:
                if attempt == 3:
                    raise AtlasProtocolError(f"0x{address:02x}: response timed out")
                self._sleep(0.3)
                continue
            if status == STATUS_SYNTAX_ERROR:
                raise AtlasProtocolError(f"0x{address:02x}: command syntax error")
            if status == STATUS_NO_DATA:
                raise AtlasProtocolError(f"0x{address:02x}: no response data")
            if status != STATUS_SUCCESS:
                raise AtlasProtocolError(
                    f"0x{address:02x}: unknown response status {status}"
                )
            return raw[1:].split(b"\x00", 1)[0].decode("ascii").strip()

        raise AtlasProtocolError(f"0x{address:02x}: response timed out")

    def write_only(self, address: int, command: str, *, processing_time: float = 0.4) -> None:
        """Send a command that intentionally reboots before returning a response."""
        self._transport.write(address, command.encode("ascii"))
        self._sleep(processing_time)

    def change_address(self, device: AtlasDevice, new_address: int) -> None:
        """Change a circuit address; the EZO reboots without a readable reply."""
        if not 1 <= new_address <= 127:
            raise ValueError("Atlas I2C address must be between 1 and 127")
        self.write_only(device.address, f"I2C,{new_address}")

    def device_command(self, device: AtlasDevice, command: str) -> str:
        """Run one explicitly confirmed non-destructive management command."""
        clean = command.strip()
        if not clean or len(clean) > 48 or not clean.isascii():
            raise ValueError("Command must be 1-48 ASCII characters")
        blocked = {"factory", "i2c", "baud", "sleep", "cal"}
        root = clean.split(",", 1)[0].lower()
        if root in blocked:
            raise ValueError(f"{root} must use its dedicated protected workflow")
        return self.command(device.address, clean, processing_time=0.7)

    def identify(self, address: int) -> AtlasDevice:
        """Identify a circuit using the read-only information command."""
        response = self.command(address, "i", processing_time=0.3)
        fields = [field.strip() for field in response.lstrip("?").split(",")]
        if len(fields) < 2 or fields[0].upper() != "I":
            raise AtlasProtocolError(f"0x{address:02x}: invalid identity {response!r}")
        return AtlasDevice(
            address=address,
            device_type=fields[1],
            firmware=fields[2] if len(fields) > 2 else None,
        )

    def discover(self, addresses=None) -> list[AtlasDevice]:
        """Probe selected addresses; default to documented EZO addresses."""
        devices: list[AtlasDevice] = []
        for address in addresses or DEFAULT_ADDRESSES:
            try:
                devices.append(self.identify(address))
            except (AtlasProtocolError, OSError):
                continue
        return devices

    def calibration_status(self, device: AtlasDevice) -> str:
        """Return the circuit calibration status without changing it."""
        return self.command(device.address, "Cal,?", processing_time=0.3)

    def calibrate(self, device: AtlasDevice, operation: str, value=None) -> str:
        """Run one explicitly requested Atlas calibration command."""
        kind = device.device_type.lower()
        if operation == "clear":
            command = "Cal,clear"
        elif kind == "ph" and operation in {"low", "mid", "high"}:
            if value is None:
                raise ValueError("pH calibration requires a reference value")
            command = f"Cal,{operation},{float(value):g}"
        elif kind == "do" and operation == "atmospheric":
            command = "Cal"
        elif kind == "do" and operation == "zero":
            command = "Cal,0"
        elif kind == "ec" and operation == "dry":
            command = "Cal,dry"
        elif kind == "ec" and operation in {"one", "low", "high"}:
            if value is None:
                raise ValueError("EC calibration requires a reference value")
            command = f"Cal,{operation},{float(value):g}"
        elif kind == "rtd" and operation == "reference":
            if value is None:
                raise ValueError("RTD calibration requires a reference value")
            command = f"Cal,{float(value):g}"
        else:
            raise ValueError(f"Unsupported {device.device_type} calibration: {operation}")
        return self.command(device.address, command, processing_time=1.3)

    def read_measurement(self, device: AtlasDevice) -> tuple[float, ...]:
        """Read the circuit and parse all numeric response fields."""
        response = self.command(device.address, "R")
        try:
            return tuple(float(value.strip()) for value in response.split(","))
        except ValueError as err:
            raise AtlasProtocolError(
                f"0x{device.address:02x}: invalid measurement {response!r}"
            ) from err
