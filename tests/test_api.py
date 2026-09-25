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
    SERIAL_QUERY,
    STATUS_QUERY,
    PaceexBmsApi,
    PaceexConnectError,
    PaceexConnectionError,
    PaceexProtocolError,
    PaceexReceiveError,
    _crc_modbus,
)


def make_frame(size: int, fill=None, query=STATUS_QUERY) -> bytes:
    """Build a valid PACEEX response frame for a request."""
    frame = bytearray(size)
    frame[0] = 0x9A
    frame[1:7] = query[1:7]
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
    """Serve one scripted response for each request on a connection."""

    def __init__(self, responses=(), send_error=None, recv_chunk_size=None):
        self._responses = [bytes(response) for response in responses]
        self._response_index = 0
        self._active_response = bytearray()
        self._send_error = send_error
        self._recv_chunk_size = recv_chunk_size
        self.sent: list[bytes] = []
        self.closed = False

    def settimeout(self, _timeout: float) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)
        if self._send_error is not None:
            raise self._send_error
        if self._response_index < len(self._responses):
            self._active_response = bytearray(self._responses[self._response_index])
            self._response_index += 1
        else:
            self._active_response = bytearray()

    def recv(self, size: int) -> bytes:
        if not self._active_response:
            return b""
        size = min(size, len(self._active_response))
        if self._recv_chunk_size is not None:
            size = min(size, self._recv_chunk_size)
        chunk = bytes(self._active_response[:size])
        del self._active_response[:size]
        return chunk

    def close(self) -> None:
        self.closed = True


class SessionTest(unittest.TestCase):
    """Test persistent TCP sessions and frame handling."""

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_read_status_uses_single_connection(self, create_connection, sleep) -> None:
        status = make_frame(62, fill_status)
        cells = make_frame(79, fill_cells, CELLS_QUERY)
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
    def test_setup_validation_uses_single_connection(
        self, create_connection, sleep
    ) -> None:
        serial_payload = b"PACEEX-TEST"
        serial = bytearray(make_frame(12 + len(serial_payload), query=SERIAL_QUERY))
        serial[8] = len(serial_payload)
        serial[9 : 9 + len(serial_payload)] = serial_payload
        serial[-3:-1] = _crc_modbus(bytes(serial[:-3])).to_bytes(2, "big")
        status = make_frame(62, fill_status)
        cells = make_frame(79, fill_cells, CELLS_QUERY)
        sock = FakeSocket([bytes(serial), status, cells])
        create_connection.return_value = sock

        info, data = PaceexBmsApi("unused").read_device_info_and_status()

        self.assertEqual(info.serial_number, "PACEEX-TEST")
        self.assertEqual(data["state_of_charge"], 80)
        self.assertEqual(create_connection.call_count, 1)
        self.assertEqual(len(sock.sent), 3)
        self.assertEqual(
            sleep.call_args_list,
            [call(QUERY_COOLDOWN), call(QUERY_COOLDOWN)],
        )

    @patch("api.socket.create_connection")
    def test_frame_reader_ignores_internal_tail_byte(self, create_connection) -> None:
        frame = bytearray(make_frame(62, fill_status))
        frame[12] = 0x9D
        frame[-3:-1] = _crc_modbus(bytes(frame[:-3])).to_bytes(2, "big")
        sock = FakeSocket([bytes(frame)], recv_chunk_size=13)
        create_connection.return_value = sock

        result = PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertEqual(result, bytes(frame))
        self.assertEqual(create_connection.call_count, 1)

    @patch("api.socket.create_connection")
    def test_frame_reader_handles_fragmented_tcp_response(
        self, create_connection
    ) -> None:
        frame = make_frame(62, fill_status)
        sock = FakeSocket([frame], recv_chunk_size=3)
        create_connection.return_value = sock

        result = PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertEqual(result, frame)

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_reconnects_once_after_unexpected_response(
        self, create_connection, sleep
    ) -> None:
        wrong = bytearray(make_frame(62, fill_status))
        wrong[3] = 0x0B
        wrong[-3:-1] = _crc_modbus(bytes(wrong[:-3])).to_bytes(2, "big")
        right = make_frame(62, fill_status)
        create_connection.side_effect = [
            FakeSocket([bytes(wrong)]),
            FakeSocket([right]),
        ]

        result = PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertEqual(result, right)
        self.assertEqual(create_connection.call_count, 2)
        self.assertEqual(sleep.call_args_list, [call(RECONNECT_COOLDOWN)])

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

        self.assertIn("closed the connection", str(ctx.exception))
        self.assertEqual(create_connection.call_count, 2)

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_protocol_error_does_not_reconnect(self, create_connection, sleep) -> None:
        bad_tail = bytearray(make_frame(11))
        bad_tail[-1] = 0
        create_connection.return_value = FakeSocket([bytes(bad_tail)])

        with self.assertRaises(PaceexProtocolError):
            PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertEqual(create_connection.call_count, 1)
        self.assertEqual(sleep.call_args_list, [])


if __name__ == "__main__":
    unittest.main()
