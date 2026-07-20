"""Local TCP client for the PACEEX Smart BMS protocol."""

from __future__ import annotations

from dataclasses import dataclass
import socket
import time

STATUS_QUERY = bytes.fromhex("9a00000a0000000019519d")
CELLS_QUERY = bytes.fromhex("9a00000a020000020101289c9d")
SERIAL_QUERY = bytes.fromhex("9a00000002000000a0c89d")
QUERY_COOLDOWN = 1


class PaceexError(Exception):
    """Base exception for PACEEX communication errors."""


class PaceexConnectionError(PaceexError):
    """Raised when the BMS cannot be reached."""


class PaceexProtocolError(PaceexError):
    """Raised for an invalid BMS response."""


@dataclass(frozen=True, slots=True)
class PaceexDeviceInfo:
    """Static device information."""

    serial_number: str


def _crc_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class PaceexBmsApi:
    """Read-only API for a network-connected PACEEX BMS."""

    def __init__(self, host: str, port: int = 8888, timeout: float = 5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def _query(self, query: bytes) -> bytes:
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(query)
                response = bytearray()
                while not response.endswith(b"\x9d"):
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)
        except (OSError, TimeoutError) as err:
            raise PaceexConnectionError(
                f"Unable to connect to PACEEX BMS at {self.host}:{self.port}"
            ) from err

        frame = bytes(response)
        if len(frame) < 11 or frame[0] != 0x9A or frame[-1] != 0x9D:
            raise PaceexProtocolError(f"Invalid PACEEX frame: {frame.hex()}")
        expected_length = 11 + frame[7]
        if len(frame) != expected_length:
            raise PaceexProtocolError(
                f"Invalid PACEEX frame length: {len(frame)}, expected {expected_length}"
            )
        received_crc = int.from_bytes(frame[-3:-1], "big")
        if _crc_modbus(frame[:-3]) != received_crc:
            raise PaceexProtocolError("Invalid PACEEX frame checksum")
        return frame

    def read_device_info(self) -> PaceexDeviceInfo:
        """Read the BMS serial number."""
        response = self._query(SERIAL_QUERY)
        length = response[8]
        serial = (
            response[9 : 9 + length].decode("ascii", errors="replace").strip("\x00 ")
        )
        if not serial:
            raise PaceexProtocolError("BMS returned an empty serial number")
        return PaceexDeviceInfo(serial_number=serial)

    def read_status(self) -> dict[str, float | int]:
        """Read system and individual cell data."""
        status = self._query(STATUS_QUERY)
        # The Wi-Fi adapter briefly stops accepting connections after a reply.
        time.sleep(QUERY_COOLDOWN)
        cells_response = self._query(CELLS_QUERY)

        cell_count = cells_response[11]
        if not 1 <= cell_count <= 32:
            raise PaceexProtocolError(f"Invalid cell count: {cell_count}")

        cells = [
            int.from_bytes(cells_response[12 + index * 4 : 14 + index * 4], "big")
            / 1000
            for index in range(cell_count)
        ]
        current = int.from_bytes(status[9:13], "big", signed=True) / 100
        voltage = int.from_bytes(status[13:17], "big") / 100

        data: dict[str, float | int] = {
            "state_of_charge": status[29],
            "state_of_health": status[30],
            "voltage": voltage,
            "current": current,
            "power": round(voltage * current, 1),
            "remaining_capacity": int.from_bytes(status[17:21], "big") / 100,
            "design_capacity": int.from_bytes(status[21:25], "big") / 100,
            "cycles": int.from_bytes(status[31:35], "big"),
            "cell_count": cell_count,
            "cell_delta": round(max(cells) - min(cells), 3),
            "cell_min_voltage": min(cells),
            "cell_max_voltage": max(cells),
        }
        data.update(
            {f"cell_{index:02d}_voltage": value for index, value in enumerate(cells, 1)}
        )
        return data
