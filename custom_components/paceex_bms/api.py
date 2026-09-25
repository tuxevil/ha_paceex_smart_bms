"""Local TCP client for the PACEEX Smart BMS protocol."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import socket
import time
from typing import Self

STATUS_QUERY = bytes.fromhex("9a00000a0000000019519d")
CELLS_QUERY = bytes.fromhex("9a00000a020000020101289c9d")
SERIAL_QUERY = bytes.fromhex("9a00000002000000a0c89d")
QUERY_COOLDOWN = 1
RECONNECT_COOLDOWN = 2

_LOGGER = logging.getLogger(__name__)


class PaceexError(Exception):
    """Base exception for PACEEX communication errors."""


class PaceexConnectionError(PaceexError):
    """Base class for PACEEX transport errors."""


class PaceexConnectError(PaceexConnectionError):
    """Raised when the TCP connection to the BMS cannot be established."""


class PaceexReceiveError(PaceexConnectionError):
    """Raised when the BMS is connected but does not return a usable reply."""


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

    def session(self) -> PaceexSession:
        """Create a session carrying one or more queries over one connection."""
        return PaceexSession(self.host, self.port, self.timeout)

    def _query(self, query: bytes) -> bytes:
        """Send a single query over a short-lived session."""
        with self.session() as sess:
            return sess.query(query)

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
        """Read system and individual cell data over a single connection."""
        with self.session() as sess:
            status = sess.query(STATUS_QUERY)
            # The Wi-Fi adapter briefly stops accepting connections after a
            # reply; pacing queries avoids hitting its busy state.
            time.sleep(QUERY_COOLDOWN)
            cells_response = sess.query(CELLS_QUERY)

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


class PaceexSession:
    """One TCP connection carrying a full poll cycle.

    The Wi-Fi adapter tolerates a persistent connection far better than
    repeated connect/query/close rounds, so every query of a cycle shares
    the same socket. At most one reconnect is attempted per query; anything
    beyond that is left to the next polling cycle instead of hammering a
    possibly busy adapter.
    """

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sock: socket.socket | None = None

    def __enter__(self) -> Self:
        self._connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _connect(self) -> None:
        try:
            self._sock = socket.create_connection(
                (self._host, self._port), self._timeout
            )
            self._sock.settimeout(self._timeout)
        except (OSError, TimeoutError) as err:
            raise PaceexConnectError(
                f"Unable to reach PACEEX BMS at {self._host}:{self._port}: {err}"
            ) from err

    def close(self) -> None:
        """Close the connection, if open."""
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def query(self, query: bytes) -> bytes:
        """Send one query, reopening the connection once if it is dead."""
        try:
            return self._query_once(query)
        except PaceexReceiveError as err:
            _LOGGER.debug("PACEEX session query failed (%s); reconnecting once", err)
            self.close()
            time.sleep(RECONNECT_COOLDOWN)
            self._connect()
            return self._query_once(query)

    def _query_once(self, query: bytes) -> bytes:
        """Send one query over the current connection without retrying."""
        sock = self._sock
        if sock is None:
            raise PaceexReceiveError("PACEEX session has no open connection")
        try:
            sock.sendall(query)
            response = bytearray()
            while not response.endswith(b"\x9d"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
        except (ConnectionResetError, BrokenPipeError) as err:
            raise PaceexReceiveError(
                f"PACEEX BMS at {self._host}:{self._port} reset the connection: {err}"
            ) from err
        except (OSError, TimeoutError) as err:
            raise PaceexReceiveError(
                f"PACEEX BMS at {self._host}:{self._port} did not answer in time: {err}"
            ) from err

        if not response:
            raise PaceexReceiveError(
                f"PACEEX BMS at {self._host}:{self._port} closed the connection "
                "without answering"
            )
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
