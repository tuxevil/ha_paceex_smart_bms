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

    @staticmethod
    def _parse_device_info(response: bytes) -> PaceexDeviceInfo:
        """Parse static device information from a serial-number response."""
        if len(response) < 12:
            raise PaceexProtocolError("BMS returned a truncated serial-number frame")
        length = response[8]
        if length > response[7] - 1:
            raise PaceexProtocolError(
                f"Invalid serial number length: {length}, "
                f"payload is {response[7]} byte(s)"
            )
        serial = (
            response[9 : 9 + length].decode("ascii", errors="replace").strip("\x00 ")
        )
        if not serial:
            raise PaceexProtocolError("BMS returned an empty serial number")
        return PaceexDeviceInfo(serial_number=serial)

    @staticmethod
    def _parse_status(status: bytes, cells_response: bytes) -> dict[str, float | int]:
        """Parse system and individual cell responses."""
        if len(status) < 35:
            raise PaceexProtocolError(
                f"Truncated PACEEX status frame: {len(status)} byte(s)"
            )
        if len(cells_response) < 12:
            raise PaceexProtocolError(
                f"Truncated PACEEX cell frame: {len(cells_response)} byte(s)"
            )

        cell_count = cells_response[11]
        if not 1 <= cell_count <= 32:
            raise PaceexProtocolError(f"Invalid cell count: {cell_count}")

        cell_data_end = 12 + (cell_count - 1) * 4 + 2
        if cell_data_end > len(cells_response) - 3:
            raise PaceexProtocolError(
                f"Truncated PACEEX cell data for {cell_count} cells: "
                f"{len(cells_response)} byte(s)"
            )

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

    @staticmethod
    def _read_device_info(sess: PaceexSession) -> PaceexDeviceInfo:
        return PaceexBmsApi._parse_device_info(sess.query(SERIAL_QUERY))

    @staticmethod
    def _read_status(sess: PaceexSession) -> dict[str, float | int]:
        status = sess.query(STATUS_QUERY)
        time.sleep(QUERY_COOLDOWN)
        cells_response = sess.query(CELLS_QUERY)
        return PaceexBmsApi._parse_status(status, cells_response)

    def read_device_info(self) -> PaceexDeviceInfo:
        """Read the BMS serial number."""
        with self.session() as sess:
            return self._read_device_info(sess)

    def read_status(self) -> dict[str, float | int]:
        """Read system and individual cell data over a single connection."""
        with self.session() as sess:
            return self._read_status(sess)

    def read_device_info_and_status(
        self,
    ) -> tuple[PaceexDeviceInfo, dict[str, float | int]]:
        """Validate device identity and telemetry over one TCP session."""
        with self.session() as sess:
            info = self._read_device_info(sess)
            time.sleep(QUERY_COOLDOWN)
            data = self._read_status(sess)
        return info, data


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
        sock: socket.socket | None = None
        try:
            sock = socket.create_connection((self._host, self._port), self._timeout)
            sock.settimeout(self._timeout)
        except (OSError, TimeoutError) as err:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            self._sock = None
            raise PaceexConnectError(
                f"Unable to reach PACEEX BMS at {self._host}:{self._port}: {err}"
            ) from err
        self._sock = sock

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

    def _recv_exact(self, size: int) -> bytes:
        """Read exactly size bytes or fail if the peer closes early."""
        sock = self._sock
        if sock is None:
            raise PaceexReceiveError("PACEEX session has no open connection")

        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise PaceexReceiveError(
                    f"PACEEX BMS at {self._host}:{self._port} closed the connection "
                    f"after {len(data)} of {size} expected byte(s)"
                )
            data.extend(chunk)
        return bytes(data)

    def _query_once(self, query: bytes) -> bytes:
        """Send one query over the current connection without retrying."""
        sock = self._sock
        if sock is None:
            raise PaceexReceiveError("PACEEX session has no open connection")
        try:
            sock.sendall(query)
            header = self._recv_exact(8)
            if header[0] != 0x9A:
                raise PaceexProtocolError(f"Invalid PACEEX frame start: {header.hex()}")
            expected_length = 11 + header[7]
            frame = header + self._recv_exact(expected_length - len(header))
            if frame[1:7] != query[1:7]:
                raise PaceexReceiveError(
                    "PACEEX BMS returned an unexpected response type: "
                    f"{frame[1:7].hex()} (expected {query[1:7].hex()})"
                )
        except (ConnectionResetError, BrokenPipeError) as err:
            raise PaceexReceiveError(
                f"PACEEX BMS at {self._host}:{self._port} reset the connection: {err}"
            ) from err
        except (OSError, TimeoutError) as err:
            raise PaceexReceiveError(
                f"PACEEX BMS at {self._host}:{self._port} did not answer in time: {err}"
            ) from err

        if frame[-1] != 0x9D:
            raise PaceexProtocolError(f"Invalid PACEEX frame tail: {frame.hex()}")
        received_crc = int.from_bytes(frame[-3:-1], "big")
        if _crc_modbus(frame[:-3]) != received_crc:
            raise PaceexProtocolError("Invalid PACEEX frame checksum")
        return frame
