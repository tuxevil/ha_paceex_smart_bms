"""Data coordinator for PACEEX BMS."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PaceexBmsApi, PaceexError
from .const import DOMAIN

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

    async def _async_update_data(self) -> dict[str, float | int]:
        try:
            return await self.hass.async_add_executor_job(self.api.read_status)
        except PaceexError as err:
            raise UpdateFailed(f"Error communicating with PACEEX BMS: {err}") from err
