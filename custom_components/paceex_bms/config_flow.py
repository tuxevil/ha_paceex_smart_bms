"""Config flow for PACEEX BMS."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .api import PaceexBmsApi, PaceexConnectionError, PaceexProtocolError
from .const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str:
    api = PaceexBmsApi(data[CONF_HOST], data[CONF_PORT])
    info = await hass.async_add_executor_job(api.read_device_info)
    await hass.async_add_executor_job(api.read_status)
    return info.serial_number


class PaceexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a PACEEX BMS config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Configure a PACEEX BMS from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                serial = await _validate_input(self.hass, user_input)
            except PaceexConnectionError:
                errors["base"] = "cannot_connect"
            except PaceexProtocolError:
                errors["base"] = "invalid_response"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                    }
                )
                return self.async_create_entry(
                    title=f"PACEEX BMS {serial}", data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
