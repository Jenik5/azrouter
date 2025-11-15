from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class AzRouterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for AZ Router integration."""
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step when user adds the integration."""

        errors: dict[str, str] = {}

        if user_input is not None:
            # Lazy import of AzRouterClient to avoid import-time failures
            try:
                from .api import AzRouterClient
            except Exception as exc:
                # If the api module can't be imported, log & surface a generic error
                self.hass.logger and self.hass.logger.debug("AZR/config_flow: failed to import api: %s", exc)
                errors["base"] = "internal_error"
                schema = vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Optional(CONF_USERNAME, default=""): str,
                        vol.Optional(CONF_PASSWORD, default=""): str,
                        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
                    }
                )
                return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

            session = async_get_clientsession(self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, True))
            client = AzRouterClient(
                user_input[CONF_HOST],
                session,
                user_input.get(CONF_USERNAME),
                user_input.get(CONF_PASSWORD),
                user_input.get(CONF_VERIFY_SSL, True),
            )

            try:
                # quick probe: login + status
                await client.login()
                await client.get_status()
                return self.async_create_entry(title=f"AZ Router ({user_input[CONF_HOST]})", data=user_input)
            except Exception as err:
                self.hass.logger and self.hass.logger.debug("AZR/config_flow: connection probe failed: %s", err)
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
