"""Discovery and guarded manual control for Waveshare Motor Driver HATs."""

from __future__ import annotations

from dataclasses import dataclass
import time


CHANNELS = {
    "A": {"pwm": 0, "direction": (1, 2)},
    "B": {"pwm": 5, "direction": (3, 4)},
}


@dataclass(frozen=True, slots=True)
class MotorHat:
    address: int
    mode1: int
    prescale: int

    @property
    def channels(self) -> list[dict]:
        """Waveshare Motor Driver HAT channel layout from the vendor driver."""
        return [
            {"id": "A", "name": "Motor A", "pwm": 0, "direction": [1, 2]},
            {"id": "B", "name": "Motor B", "pwm": 5, "direction": [3, 4]},
        ]


class WaveshareMotorHatController:
    """Drive one Waveshare channel for an explicitly bounded manual test.

    The channel map and 50 Hz PWM setup match Waveshare's reference driver.
    This class deliberately exposes no unbounded run operation to Home Assistant.
    """

    MODE1 = 0x00
    PRESCALE = 0xFE
    LED0_ON_L = 0x06
    PWM_FREQUENCY = 50

    def __init__(self, bus_number: int = 1, address: int = 0x40, bus=None) -> None:
        if bus is None:
            try:
                from smbus2 import SMBus
            except ImportError:
                from .linux_i2c import LinuxI2CBus

                bus = LinuxI2CBus(bus_number)
            else:
                bus = SMBus(bus_number)
        self._bus = bus
        self.address = address

    def close(self) -> None:
        self._bus.close()

    def _set_pwm(self, channel: int, on: int, off: int) -> None:
        register = self.LED0_ON_L + 4 * channel
        self._bus.write_i2c_block_data(
            self.address,
            register,
            [on & 0xFF, (on >> 8) & 0x0F, off & 0xFF, (off >> 8) & 0x0F],
        )

    def _set_level(self, channel: int, enabled: bool) -> None:
        self._set_pwm(channel, 0, 4095 if enabled else 0)

    def _set_frequency(self) -> None:
        prescale = round(25_000_000 / (4096 * self.PWM_FREQUENCY)) - 1
        old_mode = self._bus.read_byte_data(self.address, self.MODE1)
        sleep_mode = (old_mode & 0x7F) | 0x10
        self._bus.write_byte_data(self.address, self.MODE1, sleep_mode)
        self._bus.write_byte_data(self.address, self.PRESCALE, prescale)
        self._bus.write_byte_data(self.address, self.MODE1, old_mode)
        time.sleep(0.005)
        self._bus.write_byte_data(self.address, self.MODE1, old_mode | 0xA1)

    def stop(self, channel: str) -> None:
        layout = CHANNELS[channel]
        self._set_pwm(layout["pwm"], 0, 0)
        self._set_level(layout["direction"][0], False)
        self._set_level(layout["direction"][1], False)

    def timed_run(self, channel: str, seconds: float, speed: int = 100) -> None:
        """Run forward and guarantee stop, even when the wait is interrupted."""
        if channel not in CHANNELS:
            raise ValueError("Motor channel must be A or B")
        if not 1 <= seconds <= 30:
            raise ValueError("Motor test duration must be between 1 and 30 seconds")
        if not 20 <= speed <= 100:
            raise ValueError("Motor test speed must be between 20 and 100 percent")
        layout = CHANNELS[channel]
        self._set_frequency()
        self.stop(channel)
        try:
            self._set_level(layout["direction"][0], False)
            self._set_level(layout["direction"][1], True)
            self._set_pwm(layout["pwm"], 0, round(4095 * speed / 100))
            time.sleep(seconds)
        finally:
            self.stop(channel)


class MotorHatInventory:
    """Inspect HAT controller registers without writing or moving motors."""

    def __init__(self, bus_number: int = 1) -> None:
        try:
            from smbus2 import SMBus
        except ImportError:
            from .linux_i2c import LinuxI2CBus

            self._bus = LinuxI2CBus(bus_number)
        else:
            self._bus = SMBus(bus_number)

    def close(self) -> None:
        self._bus.close()

    def discover(self, addresses=range(0x40, 0x50)) -> list[MotorHat]:
        hats = []
        for address in addresses:
            try:
                mode1 = self._bus.read_byte_data(address, 0x00)
                prescale = self._bus.read_byte_data(address, 0xFE)
            except OSError:
                continue
            hats.append(MotorHat(address, mode1, prescale))
        return hats
