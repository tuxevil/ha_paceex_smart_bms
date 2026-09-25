"""Data coordinator for PACEEX BMS."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PaceexBmsApi, PaceexError
from .const import DOMAIN, UNAVAILABLE_AFTER_FAILURES

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
            # Diagnostic sensors are coordinator state rather than payload data,
            # so listeners must run even when the battery readings are unchanged.
            always_update=True,
        )
        self.api = api
        self.consecutive_failures = 0
        self.last_success: datetime | None = None

    async def _async_update_data(self) -> dict[str, float | int]:
        """Poll once while preserving stale data across transient outages."""
        try:
            data = await self.hass.async_add_executor_job(self.api.read_status)
        except PaceexError as err:
            self.consecutive_failures += 1
            if self.data is None:
                raise UpdateFailed(
                    f"Error communicating with PACEEX BMS during initial refresh: {err}"
                ) from err

            if self.consecutive_failures == 1:
                _LOGGER.warning(
                    "PACEEX BMS poll failed; keeping last values: %s",
                    err,
                )
            elif self.consecutive_failures == UNAVAILABLE_AFTER_FAILURES:
                _LOGGER.warning(
                    "PACEEX BMS has failed %s consecutive polls; telemetry entities "
                    "are now unavailable while diagnostics remain active: %s",
                    self.consecutive_failures,
                    err,
                )
            else:
                _LOGGER.debug(
                    "PACEEX BMS poll still failing (%s consecutive): %s",
                    self.consecutive_failures,
                    err,
                )
            return self.data

        if self.consecutive_failures:
            _LOGGER.info(
                "PACEEX BMS communication recovered after %s failed poll(s)",
                self.consecutive_failures,
            )
        self.consecutive_failures = 0
        self.last_success = datetime.now(timezone.utc)
        return data
