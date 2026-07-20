"""Tests for the PACEEX TCP API."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest
from unittest.mock import call, patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "custom_components" / "paceex_bms")
)

from api import (  # noqa: E402
    CELLS_QUERY,
    STATUS_QUERY,
    PaceexBmsApi,
    PaceexConnectionError,
    _crc_modbus,
)


class CooldownApi(PaceexBmsApi):
    """Simulate an adapter that briefly rejects a second connection."""

    def __init__(self) -> None:
        super().__init__("unused")
        self.status_completed_at: float | None = None

    def _query(self, query: bytes) -> bytes:
        if query == STATUS_QUERY:
            status = bytearray(62)
            status[29] = 80
            status[30] = 99
            self.status_completed_at = time.monotonic()
            return bytes(status)

        if query == CELLS_QUERY:
            assert self.status_completed_at is not None
            if time.monotonic() - self.status_completed_at < 0.9:
                raise PaceexConnectionError("adapter is still busy")
            cells = bytearray(12 + 4 * 16)
            cells[11] = 16
            for index in range(16):
                cells[12 + index * 4 : 14 + index * 4] = (3300 + index).to_bytes(
                    2, "big"
                )
            return bytes(cells)

        raise AssertionError("unexpected query")


class ReadStatusTest(unittest.TestCase):
    """Test combined status reads."""

    def test_waits_for_adapter_before_querying_cells(self) -> None:
        data = CooldownApi().read_status()

        self.assertEqual(data["cell_count"], 16)
        self.assertEqual(data["state_of_charge"], 80)


class FakeSocket:
    """Return one complete protocol frame."""

    def __init__(self, response: bytes) -> None:
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def settimeout(self, _timeout: float) -> None:
        pass

    def sendall(self, _query: bytes) -> None:
        pass

    def recv(self, _size: int) -> bytes:
        return self.response


class QueryRetryTest(unittest.TestCase):
    """Test recovery from transient TCP failures."""

    @patch("api.time.sleep")
    @patch("api.socket.create_connection")
    def test_retries_each_query_with_backoff(self, create_connection, sleep) -> None:
        header = bytes.fromhex("9a00000000000000")
        response = header + _crc_modbus(header).to_bytes(2, "big") + b"\x9d"
        create_connection.side_effect = [
            ConnectionResetError(),
            ConnectionResetError(),
            FakeSocket(response),
        ]

        result = PaceexBmsApi("unused")._query(STATUS_QUERY)

        self.assertEqual(result, response)
        self.assertEqual(create_connection.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(1), call(2)])


if __name__ == "__main__":
    unittest.main()
