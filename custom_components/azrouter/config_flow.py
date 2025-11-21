# custom_components/azrouter/config_flow.py
# -----------------------------------------------------------
# Config flow for AZ Router integration
# - one-step form with host/credentials
# - best-effort autodiscovery of AZ Router hostname (azrouter / azrouter.local)
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Optional
import socket
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
)

_LOGGER = logging.getLogger(__name__)


class AzRouterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for AZ Router integration."""

    VERSION = 1

    async def _auto_discover_host(self) -> Optional[str]:
        """Try to resolve AZ Router hostname on the local network.

        Returns:
            IP/hostname string if found, otherwise None.
        """
        candidate_hosts = ["azrouter.local", "azrouter"]

        for host in candidate_hosts:
            try:
                ip = await self.hass.async_add_executor_job(
                    socket.gethostbyname, host
                )
                _LOGGER.debug(
                    "Auto-discovery: hostname '%s' resolved to %s", host, ip
                )
                # vrátíme spíš hostname než IP – IP se může měnit, hostname zůstává
                return host
            except Exception as err:
                _LOGGER.debug(
                    "Auto-discovery: hostname '%s' not resolved (%s)", host, err
                )

        _LOGGER.debug("Auto-discovery: no AZ Router hostname found")
        return None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step when user adds the integration."""
        errors: dict[str, str] = {}

        # ------------------------------------------------------------------
        # User already submitted the form → ověříme připojení
        # ------------------------------------------------------------------
        if user_input is not None:
            try:
                # lazy import to avoid import-time errors
                from .api import AzRouterClient
            except Exception as exc:
                _LOGGER.debug("Failed to import AzRouterClient: %s", exc)
                errors["base"] = "internal_error"
            else:
                session = async_get_clientsession(
                    self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, True)
                )
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
                    return self.async_create_entry(
                        title=f"AZ Router ({user_input[CONF_HOST]})",
                        data=user_input,
                    )
                except Exception as err:
                    _LOGGER.debug("Connection probe failed: %s", err)
                    errors["base"] = "cannot_connect"

        # ------------------------------------------------------------------
        # First time showing the form (or previous attempt failed)
        # → zkusíme autodiscovery a hodnotu dáme jako default do CONF_HOST
        # ------------------------------------------------------------------
        autodiscovered_host = await self._auto_discover_host()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=autodiscovered_host or "",
                ): str,
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
# End Of File
