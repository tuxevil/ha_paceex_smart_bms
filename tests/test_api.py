"""Tests for the PACEEX TCP API."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "custom_components" / "paceex_bms")
)

from api import (  # noqa: E402
    CELLS_QUERY,
    STATUS_QUERY,
    PaceexBmsApi,
    PaceexConnectionError,
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


if __name__ == "__main__":
    unittest.main()
