from __future__ import annotations
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS, DEFAULT_SCAN_INTERVAL
from .api import AzRouterClient

import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_MODEL: Dict[str, str] = {
    "1": "AZ Router Smart Slave",
    "4": "AZ Charger Cube",
}


def _friendly_device_prefix(dtype: str) -> str:
    """Return friendly device prefix for a given deviceType."""
    if str(dtype) == "1":
        return "AZ Router"
    if str(dtype) == "4":
        return "AZ Charger"
    return "AZ Device"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AZ Router from a config entry.

    Steps performed:
    1) Create HTTP session and AzRouterClient, perform login.
    2) Create DataUpdateCoordinator for master data (power + status).
    3) Perform initial refresh of coordinator.
    4) Fetch devices list from device API and register device entries in device registry.
    5) Forward platform setups (sensor, switch, number, ...).
    6) Register integration services.
    """
    host = entry.data.get("host")
    username = entry.data.get("username")
    password = entry.data.get("password")
    verify_ssl = entry.data.get("verify_ssl", True)

    _LOGGER.debug("AZR/__init__: starting setup for host=%s", host)

    # 1) HTTP session + client
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = AzRouterClient(host, session, username, password, verify_ssl=verify_ssl)

    # login (may raise)
    _LOGGER.debug("AZR/__init__: logging in to device")
    await client.login()
    _LOGGER.debug("AZR/__init__: login completed")

    # 2) Coordinator for master data
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=client.async_get_all_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    # Expose client on coordinator for convenience
    coordinator.api = client

    # 3) first refresh
    try:
        _LOGGER.debug("AZR/__init__: performing first refresh of master data")
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.exception("AZR/__init__: failed first refresh of master data: %s", err)
        raise UpdateFailed(str(err)) from err

    # 4) fetch devices list from device API and register devices
    devices_list: List[Dict[str, Any]] = []
    try:
        _LOGGER.debug("AZR/__init__: fetching device list from API")
        devices_result = await client.async_get_devices_data()
        # client.async_get_devices_data expected to return dict {"devices": [...]}
        if isinstance(devices_result, dict):
            candidate = devices_result.get("devices", [])
        else:
            candidate = devices_result

        if isinstance(candidate, (list, tuple)):
            devices_list = list(candidate)
        else:
            devices_list = []
        _LOGGER.debug("AZR/__init__: fetched %d devices", len(devices_list))
    except Exception as exc:
        _LOGGER.exception("AZR/__init__: failed to fetch devices from API: %s", exc)
        devices_list = []

    # 5) persist references & data so platforms can use them
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "devices": devices_list,
    }

    # 6) forward platform setups (sensor, switch, number, ...)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ---- services: master boost + device boost ----
    async def handle_set_master_boost(call):
        enabled = bool(call.data.get("enabled"))
        _LOGGER.debug(
            "AZR/__init__: service set_master_boost called with enabled=%s",
            enabled,
        )

        await client.async_set_master_boost(enabled)
        await coordinator.async_request_refresh()

    async def handle_set_device_boost(call):
        enabled = bool(call.data.get("enabled"))
        dev_reg = dr.async_get(hass)

        # HA služba pošle device_id (string nebo list stringů)
        ha_device_ids = call.data.get("device_id") or []
        if isinstance(ha_device_ids, str):
            ha_device_ids = [ha_device_ids]

        _LOGGER.debug(
            "AZR/__init__: service set_device_boost called for HA devices=%s, enabled=%s",
            ha_device_ids,
            enabled,
        )

        for ha_dev_id in ha_device_ids:
            device = dev_reg.async_get(ha_dev_id)
            if not device:
                _LOGGER.warning(
                    "AZR/__init__: no device registry entry for id=%s",
                    ha_dev_id,
                )
                continue

            az_device_id = None

            # identifiers: [("azrouter", "01KA475Q0BXSCNAYRNA6KYBMHA_device_24")]
            for domain, ident in device.identifiers:
                if domain != DOMAIN:
                    continue

                if isinstance(ident, str) and "_device_" in ident:
                    try:
                        az_device_id = int(ident.split("_device_")[1])
                    except ValueError:
                        _LOGGER.warning(
                            "AZR/__init__: cannot parse AZ device id from identifier=%s",
                            ident,
                        )
                        continue

            if az_device_id is None:
                _LOGGER.warning(
                    "AZR/__init__: could not resolve AZ device id for HA device %s",
                    ha_dev_id,
                )
                continue

            _LOGGER.debug(
                "AZR/__init__: calling async_set_device_boost(az_device_id=%s, enabled=%s)",
                az_device_id,
                enabled,
            )
            await client.async_set_device_boost(az_device_id, enabled)

        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "set_master_boost", handle_set_master_boost)
    hass.services.async_register(DOMAIN, "set_device_boost", handle_set_device_boost)

    _LOGGER.debug(
        "AZR/__init__: setup finished successfully for entry_id=%s",
        entry.entry_id,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and cleanup resources."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # remove stored data for this entry
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # If no more entries for this integration exist, remove services
        if not hass.data[DOMAIN]:
            try:
                hass.services.async_remove(DOMAIN, "set_master_boost")
                hass.services.async_remove(DOMAIN, "set_device_boost")
            except Exception:
                _LOGGER.debug("AZR/__init__: failed to remove services")
    return unload_ok
