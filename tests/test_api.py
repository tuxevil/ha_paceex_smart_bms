"""Tests for the PACEEX TCP API."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import call, patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "custom_components" / "paceex_bms")
)

from api import (
    CELLS_QUERY,
    QUERY_COOLDOWN,
    RECONNECT_COOLDOWN,
    STATUS_QUERY,
    PaceexBmsApi,
    PaceexConnectError,
    PaceexConnectionError,
    PaceexProtocolError,
    PaceexReceiveError,
    _crc_modbus,
)


def make_frame(size: int, fill=None) -> bytes:
    """Build a valid PACEEX frame of the given total size."""
    frame = bytearray(size)
    frame[0] = 0x9A
    frame[7] = size - 11
    if fill is not None:
        fill(frame)
    frame[-3:-1] = _crc_modbus(bytes(frame[:-3])).to_bytes(2, "big")
    frame[-1] = 0x9D
    return bytes(frame)


def fill_status(frame: bytearray) -> None:
    frame[29] = 80
    frame[30] = 99


def fill_cells(frame: bytearray) -> None:
    frame[11] = 16
    for index in range(16):
        frame[12 + index * 4 : 14 + index * 4] = (3300 + index).to_bytes(2, "big")


class FakeSocket:
    """Serve a scripted sequence of responses on one connection."""

    def __init__(self, responses=(), send_error=None):
        self._responses = list(responses)
        self._send_error = send_error
        self.sent: list[bytes] = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def settimeout(self, _timeout: float) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)
        if self._send_error is not None:
            raise self._send_error

    def recv(self, _size: int) -> bytes:
        if not self._responses:
            return b""
        return self._responses.pop(0)

    def close(self) -> None:
        self.closed = True


class SessionTest(unittest.TestCase):
    """Test the single-connection poll cycle."""

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_read_status_uses_single_connection(self, create_connection, sleep) -> None:
        status = make_frame(62, fill_status)
        cells = make_frame(76, fill_cells)
        sock = FakeSocket([status, cells])
        create_connection.return_value = sock

        data = PaceexBmsApi("unused").read_status()

        self.assertEqual(data["cell_count"], 16)
        self.assertEqual(data["state_of_charge"], 80)
        self.assertEqual(create_connection.call_count, 1)
        self.assertEqual(sock.sent, [STATUS_QUERY, CELLS_QUERY])
        self.assertEqual(sleep.call_args_list, [call(QUERY_COOLDOWN)])
        self.assertTrue(sock.closed)

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_reconnects_once_after_reset(self, create_connection, sleep) -> None:
        status = make_frame(62, fill_status)
        dead = FakeSocket(send_error=ConnectionResetError())
        live = FakeSocket([status])
        create_connection.side_effect = [dead, live]

        result = PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertEqual(result, status)
        self.assertEqual(create_connection.call_count, 2)
        self.assertEqual(sleep.call_args_list, [call(RECONNECT_COOLDOWN)])

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_connect_failure_is_typed(self, create_connection, sleep) -> None:
        create_connection.side_effect = ConnectionRefusedError("refused")

        with self.assertRaises(PaceexConnectError) as ctx:
            PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertIsInstance(ctx.exception, PaceexConnectionError)
        self.assertIn("refused", str(ctx.exception))

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_closed_connection_is_typed(self, create_connection, sleep) -> None:
        create_connection.side_effect = [FakeSocket(), FakeSocket()]

        with self.assertRaises(PaceexReceiveError) as ctx:
            PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertIn("without answering", str(ctx.exception))
        self.assertEqual(create_connection.call_count, 2)

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_protocol_error_does_not_reconnect(self, create_connection, sleep) -> None:
        create_connection.return_value = FakeSocket([b"\x9a\x00garbage\x9d"])

        with self.assertRaises(PaceexProtocolError):
            PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertEqual(create_connection.call_count, 1)


if __name__ == "__main__":
    unittest.main()
