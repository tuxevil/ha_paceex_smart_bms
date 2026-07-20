"""PACEEX BMS integration."""

from __future__ import annotations

from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .api import PaceexBmsApi
from .const import CONF_PORT, CONF_SCAN_INTERVAL, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL
from .coordinator import PaceexDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR]
PaceexConfigEntry: TypeAlias = ConfigEntry[PaceexDataUpdateCoordinator]


async def _async_update_listener(hass: HomeAssistant, entry: PaceexConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: PaceexConfigEntry) -> bool:
    """Set up PACEEX BMS from a config entry."""
    api = PaceexBmsApi(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    coordinator = PaceexDataUpdateCoordinator(
        hass,
        entry,
        api,
        entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PaceexConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
