"""Data coordinator for PACEEX BMS."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PaceexBmsApi, PaceexError
from .const import DOMAIN, STALE_DATA_TOLERANCE

_LOGGER = logging.getLogger(__name__)


class PaceexDataUpdateCoordinator(DataUpdateCoordinator[dict[str, float | int]]):
    """Coordinate a single BMS poll for all sensor entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: PaceexBmsApi,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            always_update=False,
        )
        self.api = api
        self.consecutive_failures = 0
        self.last_success: datetime | None = None

    async def _async_update_data(self) -> dict[str, float | int]:
        # Single attempt per cycle: the API already reconnects once when the
        # adapter drops a query, so hammering a busy adapter with immediate
        # full re-polls only makes recovery slower.
        try:
            data = await self.hass.async_add_executor_job(self.api.read_status)
        except PaceexError as err:
            self.consecutive_failures += 1
            if self.data is None or self.consecutive_failures > STALE_DATA_TOLERANCE:
                raise UpdateFailed(
                    f"Error communicating with PACEEX BMS "
                    f"({self.consecutive_failures} consecutive failures): {err}"
                ) from err
            _LOGGER.warning(
                "PACEEX BMS poll failed (%s consecutive); keeping last values: %s",
                self.consecutive_failures,
                err,
            )
            return self.data
        self.consecutive_failures = 0
        self.last_success = datetime.now(timezone.utc)
        return data
