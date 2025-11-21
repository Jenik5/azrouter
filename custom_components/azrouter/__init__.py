# custom_components/azrouter/__init__.py
# -----------------------------------------------------------
# Integration setup for AZ Router
# - creates AzRouterClient and DataUpdateCoordinator
# - fetches master data and devices list
# - registers platforms (sensor, switch, number)
# - exposes services (master/device boost, deviceType1 & deviceType4 settings)
# -----------------------------------------------------------

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS, DEFAULT_SCAN_INTERVAL
from .api import AzRouterClient

_LOGGER = logging.getLogger(__name__)

# Mapping deviceType -> model name (for potential device_info usage)
DEVICE_TYPE_MODEL: Dict[str, str] = {
    "1": "AZ Router Smart Slave",
    "4": "AZ Charger Cube",
    "5": "Inverter",
}

SERVICE_SET_MASTER_BOOST = "set_master_boost"
SERVICE_SET_DEVICE_BOOST = "set_device_boost"
SERVICE_SET_DEVICE_TYPE_1_TEMPS = "set_device_type_1_temperatures"
SERVICE_SET_DEVICE_TYPE_1_MAX_POWER = "set_device_type_1_max_power"
SERVICE_SET_DEVICE_TYPE_4_MANUAL_POWER = "set_device_type_4_manual_power"


def _friendly_device_prefix(dtype: str) -> str:
    """Return friendly device prefix for a given deviceType."""
    if str(dtype) == "1":
        return "AZ Router"
    if str(dtype) == "4":
        return "AZ Charger"
    if str(dtype) == "5":
        return "Inverter"
    return "AZ Device"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AZ Router from a config entry.

    Steps performed:
    1) Create HTTP session and AzRouterClient, perform login.
    2) Create DataUpdateCoordinator for master data (power + status + devices + settings).
    3) Perform initial refresh of coordinator.
    4) Fetch devices list from device API and store it for platforms.
    5) Forward platform setups (sensor, switch, number, ...).
    6) Register integration services (master/device boost + device_type_1 & device_type_4 settings).
    """
    host = entry.data.get("host")
    username = entry.data.get("username")
    password = entry.data.get("password")
    verify_ssl = entry.data.get("verify_ssl", True)

    _LOGGER.debug("Starting setup for host=%s", host)

    # 1) HTTP session + client
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = AzRouterClient(host, session, username, password, verify_ssl=verify_ssl)

    # login (may raise)
    _LOGGER.debug("Logging in to device")
    await client.login()
    _LOGGER.debug("Login completed")

    # 2) Coordinator for all data (power + status + devices + settings)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=client.async_get_all_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    # Expose client on coordinator for convenience
    coordinator.api = client

    # Allow API client to see latest coordinator data
    coordinator.async_add_listener(
        lambda: setattr(client, "_last_coordinator_data", coordinator.data)
    )
    client._last_coordinator_data = coordinator.data

    # 3) first refresh
    try:
        _LOGGER.debug("Performing first refresh of master data")
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.exception("Failed first refresh of master data: %s", err)
        raise UpdateFailed(str(err)) from err

    # 4) fetch devices list from device API and store for platforms
    devices_list: List[Dict[str, Any]] = []
    try:
        _LOGGER.debug("Fetching device list from API")
        devices_result = await client.async_get_devices_data()
        # client.async_get_devices_data is expected to return dict {"devices": [...]}
        if isinstance(devices_result, dict):
            candidate = devices_result.get("devices", [])
        else:
            candidate = devices_result

        if isinstance(candidate, (list, tuple)):
            devices_list = list(candidate)
        else:
            devices_list = []

        _LOGGER.debug("Fetched %d devices from API", len(devices_list))
    except Exception as exc:
        _LOGGER.exception("Failed to fetch devices from API: %s", exc)
        devices_list = []

    # 5) persist references & data so platforms can use them
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "devices": devices_list,
    }

    # 6) forward platform setups (sensor, switch, number, ...)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # =====================================================================================
    #   HELPER: convert HA device_id -> list of AZ device_id (common.id)
    # =====================================================================================

    def _resolve_az_device_ids_from_call(call) -> list[int]:
        """Resolve AZ device IDs from HA service call (device_id → identifiers)."""
        dev_reg = dr.async_get(hass)

        ha_device_ids = call.data.get("device_id") or []
        if isinstance(ha_device_ids, str):
            ha_device_ids = [ha_device_ids]

        az_ids: list[int] = []

        for ha_dev_id in ha_device_ids:
            device = dev_reg.async_get(ha_dev_id)
            if not device:
                _LOGGER.warning("No device registry entry for id=%s", ha_dev_id)
                continue

            az_device_id = None

            # identifiers: [("azrouter", "..._device_24")]
            for domain, ident in device.identifiers:
                if domain != DOMAIN:
                    continue

                if isinstance(ident, str) and "_device_" in ident:
                    try:
                        az_device_id = int(ident.split("_device_")[1])
                    except ValueError:
                        _LOGGER.warning(
                            "Cannot parse AZ device id from identifier=%s", ident
                        )
                        continue

            if az_device_id is None:
                _LOGGER.warning(
                    "Could not resolve AZ device id for HA device %s", ha_dev_id
                )
                continue

            az_ids.append(az_device_id)

        return az_ids

    # =====================================================================================
    #   SERVICES: master boost + device boost
    # =====================================================================================

    async def handle_set_master_boost(call):
        enabled = bool(call.data.get("enabled"))
        _LOGGER.debug(
            "Service %s called with enabled=%s",
            SERVICE_SET_MASTER_BOOST,
            enabled,
        )

        await client.async_set_master_boost(enabled)
        await coordinator.async_request_refresh()

    async def handle_set_device_boost(call):
        enabled = bool(call.data.get("enabled"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s, enabled=%s",
            SERVICE_SET_DEVICE_BOOST,
            az_ids,
            enabled,
        )

        for az_device_id in az_ids:
            _LOGGER.debug(
                "Calling async_set_device_boost(az_device_id=%s, enabled=%s)",
                az_device_id,
                enabled,
            )
            await client.async_set_device_boost(az_device_id, enabled)

        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MASTER_BOOST,
        handle_set_master_boost,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DEVICE_BOOST,
        handle_set_device_boost,
    )

    # =====================================================================================
    #   SERVICES FOR DEVICE_TYPE_1 (Smart Slave) – delegated to number.py
    # =====================================================================================

    async def handle_set_device_type_1_max_power(call):
        """Service handler azrouter.set_device_type_1_max_power.

        - Selects devices via HA device target
        - For each AZ device_id calls helper in number.py
        """
        max_power = call.data.get("max_power")
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s, max_power=%s",
            SERVICE_SET_DEVICE_TYPE_1_MAX_POWER,
            az_ids,
            max_power,
        )

        # Import inside handler to avoid cyclic imports
        from .number import async_service_set_device_type_1_max_power

        for az_device_id in az_ids:
            await async_service_set_device_type_1_max_power(
                hass=hass,
                client=client,
                coordinator=coordinator,
                device_id=az_device_id,
                max_power=max_power,
            )

        await coordinator.async_request_refresh()

    async def handle_set_device_type_1_temperatures(call):
        """Service handler azrouter.set_device_type_1_temperatures.

        - target_temperature: None/0 => no change
        - boost_temperature:  None/0 => no change
        """
        target_temperature = call.data.get("target_temperature")
        boost_temperature = call.data.get("boost_temperature")
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s, "
            "target_temperature=%s, boost_temperature=%s",
            SERVICE_SET_DEVICE_TYPE_1_TEMPS,
            az_ids,
            target_temperature,
            boost_temperature,
        )

        from .number import async_service_set_device_type_1_temperatures

        for az_device_id in az_ids:
            await async_service_set_device_type_1_temperatures(
                hass=hass,
                client=client,
                coordinator=coordinator,
                device_id=az_device_id,
                target_temperature=target_temperature,
                boost_temperature=boost_temperature,
            )

        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DEVICE_TYPE_1_MAX_POWER,
        handle_set_device_type_1_max_power,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DEVICE_TYPE_1_TEMPS,
        handle_set_device_type_1_temperatures,
    )

    # =====================================================================================
    #   SERVICE FOR DEVICE_TYPE_4 (Wallbox manual power) – delegated to number.py
    # =====================================================================================

    async def handle_set_device_type_4_manual_power(call):
        """Service handler azrouter.set_device_type_4_manual_power.

        - Selects devices via HA device target
        - For each AZ device_id calls helper in number.py
        """
        manual_power = call.data.get("manual_power")
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s, manual_power=%s",
            SERVICE_SET_DEVICE_TYPE_4_MANUAL_POWER,
            az_ids,
            manual_power,
        )

        from .number import async_service_set_device_type_4_manual_power

        for az_device_id in az_ids:
            await async_service_set_device_type_4_manual_power(
                hass=hass,
                client=client,
                coordinator=coordinator,
                device_id=az_device_id,
                manual_power=manual_power,
            )

        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DEVICE_TYPE_4_MANUAL_POWER,
        handle_set_device_type_4_manual_power,
    )

    _LOGGER.debug(
        "Setup finished successfully for entry_id=%s",
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
                hass.services.async_remove(DOMAIN, SERVICE_SET_MASTER_BOOST)
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_BOOST)
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_MAX_POWER)
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_TEMPS)
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_MANUAL_POWER
                )
            except Exception:
                _LOGGER.debug("Failed to remove services during unload")
    return unload_ok

# End Of File
