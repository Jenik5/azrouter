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
from urllib.parse import urlparse

import aiohttp
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
    _reauth_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    def _normalize_host(host: str) -> str:
        """Normalize host input for stable unique_id usage."""
        raw = (host or "").strip()
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        netloc = parsed.netloc or parsed.path
        return netloc.rstrip("/").lower()

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
                    await client.async_login()
                    status = await client.async_get_status()

                    unique_source = self._normalize_host(user_input[CONF_HOST])
                    system = status.get("system") if isinstance(status, dict) else None
                    serial = system.get("sn") if isinstance(system, dict) else None
                    if isinstance(serial, (str, int)) and str(serial).strip():
                        unique_source = f"{unique_source}_{serial}"

                    await self.async_set_unique_id(unique_source)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"AZ Router ({user_input[CONF_HOST]})",
                        data=user_input,
                    )
                except aiohttp.ClientResponseError as err:
                    if err.status in (401, 403):
                        errors["base"] = "invalid_auth"
                    else:
                        errors["base"] = "cannot_connect"
                except ValueError:
                    errors["base"] = "invalid_auth"
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

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start reauth flow from an existing entry."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Confirm updated credentials for reauth."""
        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        current_data = self._reauth_entry.data

        if user_input is not None:
            merged = {
                **current_data,
                CONF_USERNAME: user_input.get(CONF_USERNAME, ""),
                CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                CONF_VERIFY_SSL: user_input.get(
                    CONF_VERIFY_SSL, current_data.get(CONF_VERIFY_SSL, True)
                ),
            }

            from .api import AzRouterClient

            session = async_get_clientsession(
                self.hass, verify_ssl=merged.get(CONF_VERIFY_SSL, True)
            )
            client = AzRouterClient(
                merged[CONF_HOST],
                session,
                merged.get(CONF_USERNAME),
                merged.get(CONF_PASSWORD),
                merged.get(CONF_VERIFY_SSL, True),
            )

            try:
                await client.async_login()
                await client.async_get_status()
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates=merged,
                )
            except aiohttp.ClientResponseError as err:
                if err.status in (401, 403):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.debug("Reauth connection probe failed: %s", err)
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Optional(CONF_USERNAME, default=current_data.get(CONF_USERNAME, "")): str,
                vol.Optional(CONF_PASSWORD, default=current_data.get(CONF_PASSWORD, "")): str,
                vol.Optional(
                    CONF_VERIFY_SSL, default=current_data.get(CONF_VERIFY_SSL, True)
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )
# End Of File
