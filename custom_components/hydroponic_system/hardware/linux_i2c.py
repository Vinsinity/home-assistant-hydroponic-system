"""Minimal Linux I2C transport with no third-party Python dependency.

The Raspberry Pi appliance deliberately ships a small system Python.  This
module talks to ``/dev/i2c-N`` through the kernel ``I2C_RDWR`` ioctl so Atlas
EZO and PCA9685 discovery do not depend on ``smbus2`` being installed.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Iterable


I2C_M_RD = 0x0001
I2C_RDWR = 0x0707


class _I2CMessage(ctypes.Structure):
    _fields_ = (
        ("addr", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("length", ctypes.c_uint16),
        ("buf", ctypes.POINTER(ctypes.c_uint8)),
    )


class _I2CRdwrData(ctypes.Structure):
    _fields_ = (
        ("msgs", ctypes.POINTER(_I2CMessage)),
        ("nmsgs", ctypes.c_uint32),
    )


class LinuxI2CBus:
    """Small subset of SMBus operations used by GrowAsist drivers."""

    def __init__(self, bus_number: int = 1, *, path: str | Path | None = None) -> None:
        self.path = Path(path or f"/dev/i2c-{int(bus_number)}")
        self._fd = os.open(self.path, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._libc.ioctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p)
        self._libc.ioctl.restype = ctypes.c_int

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _transfer(
        self,
        operations: Iterable[tuple[int, bool, bytes | int]],
    ) -> list[bytes]:
        buffers = []
        messages = []
        read_indexes: list[int] = []
        for address, read, value in operations:
            if read:
                length = int(value)
                if length <= 0:
                    raise ValueError("I2C read length must be positive")
                buffer = (ctypes.c_uint8 * length)()
                read_indexes.append(len(buffers))
            else:
                payload = bytes(value)
                if not payload:
                    raise ValueError("I2C write payload cannot be empty")
                length = len(payload)
                buffer = (ctypes.c_uint8 * length)(*payload)
            buffers.append(buffer)
            messages.append(
                _I2CMessage(
                    addr=int(address),
                    flags=I2C_M_RD if read else 0,
                    length=length,
                    buf=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8)),
                )
            )
        if not messages:
            return []
        message_array = (_I2CMessage * len(messages))(*messages)
        request = _I2CRdwrData(message_array, len(messages))
        result = self._libc.ioctl(self._fd, I2C_RDWR, ctypes.byref(request))
        if result < 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, os.strerror(error_number), str(self.path))
        return [bytes(buffers[index]) for index in read_indexes]

    def write(self, address: int, payload: bytes) -> None:
        self._transfer(((address, False, payload),))

    def read(self, address: int, length: int) -> bytes:
        return self._transfer(((address, True, length),))[0]

    def read_byte_data(self, address: int, register: int) -> int:
        return self._transfer(
            (
                (address, False, bytes((register & 0xFF,))),
                (address, True, 1),
            )
        )[0][0]

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        self.write(address, bytes((register & 0xFF, value & 0xFF)))

    def write_i2c_block_data(
        self, address: int, register: int, values: Iterable[int]
    ) -> None:
        payload = bytes((register & 0xFF, *(int(value) & 0xFF for value in values)))
        self.write(address, payload)

    def __enter__(self) -> "LinuxI2CBus":
        return self

    def __exit__(self, *_args) -> None:
        self.close()
