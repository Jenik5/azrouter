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
from dataclasses import dataclass
from typing import Any, Dict, Callable
import copy

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS, DEFAULT_SCAN_INTERVAL
from .api import AzRouterClient
from .devices.device_type_4.helpers import (
    MODE_HDO,
    MODE_PRIORITIZE_WHEN_CONNECTED,
    MODE_TIME_WINDOW,
    ensure_mode_entry,
)

_LOGGER = logging.getLogger(__name__)

# Mapping deviceType -> model name (for potential device_info usage)
DEVICE_TYPE_MODEL: Dict[str, str] = {
    "1": "AZ Router Smart Slave",
    "4": "AZ Charger Cube",
    "5": "Inverter",
}

SERVICE_SET_MASTER_BOOST = "set_master_boost"
SERVICE_SET_DEVICE_BOOST = "set_device_boost"
SERVICE_SET_DEVICE_TYPE_1_KEEP_HEATED = "set_device_type_1_keep_heated"
SERVICE_SET_DEVICE_TYPE_1_BLOCK_SOLAR_HEATING = "set_device_type_1_block_solar_heating"
SERVICE_SET_DEVICE_TYPE_1_BLOCK_HEATING_FROM_BATTERY = "set_device_type_1_block_heating_from_battery"
SERVICE_SET_DEVICE_TYPE_1_ALLOW_SOLAR_HEATING_ONLY_IN_TIME_WINDOW = (
    "set_device_type_1_allow_solar_heating_only_in_time_window"
)
SERVICE_SET_DEVICE_TYPE_1_BOOST_MODE = "set_device_type_1_boost_mode"
SERVICE_SET_DEVICE_TYPE_1_CONNECTED_PHASE = "set_device_type_1_connected_phase"
SERVICE_SET_DEVICE_TYPE_1_TEMPS = "set_device_type_1_temperatures"
SERVICE_SET_DEVICE_TYPE_1_MAX_POWER = "set_device_type_1_max_power"
SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING = "set_device_type_4_block_charging"
SERVICE_SET_DEVICE_TYPE_4_PRIORITIZE_WHEN_CONNECTED = (
    "set_device_type_4_prioritize_when_connected"
)
SERVICE_SET_DEVICE_TYPE_4_BLOCK_SOLAR_CHARGING = (
    "set_device_type_4_block_solar_charging"
)
SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING_FROM_BATTERY = (
    "set_device_type_4_block_charging_from_battery"
)
SERVICE_SET_DEVICE_TYPE_4_ALLOW_SOLAR_CHARGING_ONLY_IN_TIME_WINDOW = (
    "set_device_type_4_allow_solar_charging_only_in_time_window"
)
SERVICE_SET_DEVICE_TYPE_4_TRIGGER_PHASE = "set_device_type_4_trigger_phase"
SERVICE_SET_DEVICE_TYPE_4_APPLY_ONLY_IF_CLOUD_IS_OFFLINE = (
    "set_device_type_4_apply_only_if_cloud_is_offline"
)
SERVICE_SET_DEVICE_TYPE_4_TIME_WINDOW_CHARGING_ENABLED = (
    "set_device_type_4_time_window_charging_enabled"
)
SERVICE_SET_DEVICE_TYPE_4_HDO_CHARGING_ENABLED = (
    "set_device_type_4_hdo_charging_enabled"
)
SERVICE_SET_DEVICE_TYPE_4_MANUAL_POWER = "set_device_type_4_manual_power"


@dataclass
class AzRouterRuntimeData:
    """Runtime integration state stored on the config entry."""

    client: AzRouterClient
    coordinator: DataUpdateCoordinator


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
    try:
        await client.async_login()
    except aiohttp.ClientResponseError as err:
        if err.status in (401, 403):
            raise ConfigEntryAuthFailed("Authentication failed") from err
        raise ConfigEntryNotReady(f"Unable to connect to {host}") from err
    except ValueError as err:
        raise ConfigEntryAuthFailed("Authentication failed") from err
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to connect to {host}") from err
    _LOGGER.debug("Login completed")

    # 2) Coordinator for all data (power + status + devices + settings)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=client.async_get_all_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    # 3) first refresh
    try:
        _LOGGER.debug("Performing first refresh of master data")
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        _LOGGER.exception("Failed first refresh of master data: %s", err)
        raise ConfigEntryNotReady(f"Failed initial data refresh for {host}") from err

    # 4) persist runtime references for platforms
    entry.runtime_data = AzRouterRuntimeData(client=client, coordinator=coordinator)

    # 5) forward platform setups (sensor, switch, number, ...)
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
                        az_device_id = int(ident.rsplit("_", 1)[1])
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

    async def _find_device_payload(
        az_device_id: int,
        expected_device_type: str,
    ) -> Dict[str, Any] | None:
        """Load current device payload for a given deviceType from API devices list."""
        try:
            devices = await client.async_get_devices()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to load devices while preparing service write for device=%s: %s",
                az_device_id,
                exc,
            )
            return None

        for dev in devices:
            try:
                if (
                    str(dev.get("deviceType")) == str(expected_device_type)
                    and int(dev.get("common", {}).get("id", -1)) == int(az_device_id)
                ):
                    return dev
            except Exception:
                continue
        return None

    async def _mutate_device_settings_and_post(
        az_device_id: int,
        expected_device_type: str,
        mutator: Callable[[Dict[str, Any]], None],
        *,
        action: str,
    ) -> bool:
        """Load device payload, mutate each settings[] item, and POST."""
        root = await _find_device_payload(az_device_id, expected_device_type)
        if not root:
            _LOGGER.warning(
                "Service %s: device_type=%s id=%s not found",
                action,
                expected_device_type,
                az_device_id,
            )
            return False

        payload = copy.deepcopy(root)
        settings_list = payload.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            _LOGGER.warning(
                "Service %s: device_type=%s id=%s has no settings[]",
                action,
                expected_device_type,
                az_device_id,
            )
            return False

        for idx, item in enumerate(settings_list):
            if not isinstance(item, dict):
                item = {}
                settings_list[idx] = item
            mutator(item)

        await client.async_post_device_settings(payload)
        return True

    async def _handle_device_type_4_settings_enabled_service(
        call,
        *,
        service_name: str,
        mutator: Callable[[Dict[str, Any], bool], None],
    ) -> None:
        enabled = bool(call.data.get("enabled"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s enabled=%s",
            service_name,
            az_ids,
            enabled,
        )

        for az_device_id in az_ids:
            def _mutate(item: Dict[str, Any]) -> None:
                mutator(item, enabled)

            await _mutate_device_settings_and_post(
                az_device_id,
                "4",
                _mutate,
                action=service_name,
            )

        await coordinator.async_request_refresh()

    def _parse_boost_mode(raw_mode: Any) -> int:
        """Parse boost mode from service payload (string alias or integer)."""
        mode_map = {
            "manual": 0,
            "hdo": 1,
            "window": 2,
            "window+hdo": 3,
            "window_hdo": 3,
            "window-hdo": 3,
        }

        if isinstance(raw_mode, str):
            normalized = raw_mode.strip().lower()
            if normalized in mode_map:
                return mode_map[normalized]
            if normalized.isdigit():
                raw_mode = int(normalized)
            else:
                raise HomeAssistantError(
                    f"Unsupported boost mode '{raw_mode}'. Use manual|hdo|window|window+hdo or 0..3."
                )

        try:
            mode = int(raw_mode)
        except Exception as exc:
            raise HomeAssistantError("Boost mode must be one of 0,1,2,3.") from exc

        if mode not in (0, 1, 2, 3):
            raise HomeAssistantError("Boost mode must be one of 0,1,2,3.")
        return mode

    def _parse_trigger_phase(raw_phase: Any) -> int:
        """Parse wallbox trigger phase from L1/L2/L3 or 1..3 / 0..2."""
        if isinstance(raw_phase, str):
            normalized = raw_phase.strip().upper()
            if normalized == "L1":
                return 0
            if normalized == "L2":
                return 1
            if normalized == "L3":
                return 2
            raw_phase = normalized

        try:
            phase = int(raw_phase)
        except Exception as exc:
            raise HomeAssistantError("Phase must be L1, L2, L3 or 1, 2, 3.") from exc

        if phase == 0:
            return 0
        if phase in (1, 2, 3):
            return phase - 1
        raise HomeAssistantError("Phase must be L1, L2, L3 or 1, 2, 3.")

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

    if not hass.services.has_service(DOMAIN, SERVICE_SET_MASTER_BOOST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_MASTER_BOOST,
            handle_set_master_boost,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_BOOST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_BOOST,
            handle_set_device_boost,
        )

    # =====================================================================================
    #   SERVICES FOR DEVICE_TYPE_1 (Smart Slave) – delegated to number.py / switch.py
    # =====================================================================================
    #
    async def handle_set_device_type_1_keep_heated(call):
        enabled = bool(call.data.get("enabled"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s enabled=%s",
            SERVICE_SET_DEVICE_TYPE_1_KEEP_HEATED,
            az_ids,
            enabled,
        )

        for az_device_id in az_ids:
            await client.async_set_device_type_1_power_setting(
                az_device_id,
                "ignore_cycle",
                1 if enabled else 0,
            )

        await coordinator.async_request_refresh()

    async def handle_set_device_type_1_block_solar_heating(call):
        enabled = bool(call.data.get("enabled"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "AZR/__init__: service set_device_type_1_block_solar_heating called for AZ devices=%s enabled=%s",
            az_ids,
            enabled,
        )

        for az_device_id in az_ids:

            await client.async_set_device_type_1_power_setting(
                az_device_id,
                "block_solar_heating",
                1 if enabled else 0,
            )

        await coordinator.async_request_refresh()


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

    async def handle_set_device_type_1_block_heating_from_battery(call):
        enabled = bool(call.data.get("enabled"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s enabled=%s",
            SERVICE_SET_DEVICE_TYPE_1_BLOCK_HEATING_FROM_BATTERY,
            az_ids,
            enabled,
        )

        for az_device_id in az_ids:
            await client.async_set_device_type_1_power_setting(
                az_device_id,
                "block_heating_from_battery",
                1 if enabled else 0,
            )

        await coordinator.async_request_refresh()

    async def handle_set_device_type_1_allow_solar_heating_only_in_time_window(call):
        enabled = bool(call.data.get("enabled"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s enabled=%s",
            SERVICE_SET_DEVICE_TYPE_1_ALLOW_SOLAR_HEATING_ONLY_IN_TIME_WINDOW,
            az_ids,
            enabled,
        )

        for az_device_id in az_ids:
            def _mutate(item: Dict[str, Any]) -> None:
                power = item.setdefault("power", {})
                allowed = power.setdefault("allowed_solar_heating_time", {})
                allowed["enabled"] = 1 if enabled else 0

            await _mutate_device_settings_and_post(
                az_device_id,
                "1",
                _mutate,
                action=SERVICE_SET_DEVICE_TYPE_1_ALLOW_SOLAR_HEATING_ONLY_IN_TIME_WINDOW,
            )

        await coordinator.async_request_refresh()

    async def handle_set_device_type_1_boost_mode(call):
        mode = _parse_boost_mode(call.data.get("mode"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s mode=%s",
            SERVICE_SET_DEVICE_TYPE_1_BOOST_MODE,
            az_ids,
            mode,
        )

        for az_device_id in az_ids:
            def _mutate(item: Dict[str, Any]) -> None:
                boost = item.setdefault("boost", {})
                boost["mode"] = mode

            await _mutate_device_settings_and_post(
                az_device_id,
                "1",
                _mutate,
                action=SERVICE_SET_DEVICE_TYPE_1_BOOST_MODE,
            )

        await coordinator.async_request_refresh()

    async def handle_set_device_type_1_connected_phase(call):
        enabled = bool(call.data.get("enabled"))
        phase_raw = call.data.get("phase")
        try:
            phase = int(phase_raw)
        except Exception as exc:
            raise HomeAssistantError("Phase must be 1, 2 or 3.") from exc
        if phase not in (1, 2, 3):
            raise HomeAssistantError("Phase must be 1, 2 or 3.")

        az_ids = _resolve_az_device_ids_from_call(call)
        _LOGGER.debug(
            "Service %s called for AZ devices=%s phase=%s enabled=%s",
            SERVICE_SET_DEVICE_TYPE_1_CONNECTED_PHASE,
            az_ids,
            phase,
            enabled,
        )

        for az_device_id in az_ids:
            await client.async_set_device_type_1_connected_phase(
                az_device_id,
                phase_index=phase - 1,
                enabled=enabled,
            )

        await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_KEEP_HEATED):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_KEEP_HEATED,
            handle_set_device_type_1_keep_heated,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_BLOCK_SOLAR_HEATING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_BLOCK_SOLAR_HEATING,
            handle_set_device_type_1_block_solar_heating,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_BLOCK_HEATING_FROM_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_BLOCK_HEATING_FROM_BATTERY,
            handle_set_device_type_1_block_heating_from_battery,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_ALLOW_SOLAR_HEATING_ONLY_IN_TIME_WINDOW):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_ALLOW_SOLAR_HEATING_ONLY_IN_TIME_WINDOW,
            handle_set_device_type_1_allow_solar_heating_only_in_time_window,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_BOOST_MODE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_BOOST_MODE,
            handle_set_device_type_1_boost_mode,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_CONNECTED_PHASE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_CONNECTED_PHASE,
            handle_set_device_type_1_connected_phase,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_MAX_POWER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_MAX_POWER,
            handle_set_device_type_1_max_power,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_TEMPS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_1_TEMPS,
            handle_set_device_type_1_temperatures,
        )

    # =====================================================================================
    #   SERVICES FOR DEVICE_TYPE_4 (Wallbox)
    # =====================================================================================

    async def handle_set_device_type_4_block_charging(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            charge["block_charging"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_prioritize_when_connected(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            mode = ensure_mode_entry(charge, MODE_PRIORITIZE_WHEN_CONNECTED)
            mode["enabled"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_PRIORITIZE_WHEN_CONNECTED,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_block_solar_charging(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            charge["block_solar_charging"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_BLOCK_SOLAR_CHARGING,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_block_charging_from_battery(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            charge["block_charging_from_battery"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING_FROM_BATTERY,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_allow_solar_charging_only_in_time_window(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            allowed = charge.setdefault("allowed_solar_charging_time", {})
            allowed["enabled"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_ALLOW_SOLAR_CHARGING_ONLY_IN_TIME_WINDOW,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_apply_only_if_cloud_is_offline(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            charge["offline_only"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_APPLY_ONLY_IF_CLOUD_IS_OFFLINE,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_time_window_charging_enabled(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            mode = ensure_mode_entry(charge, MODE_TIME_WINDOW)
            mode["enabled"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_TIME_WINDOW_CHARGING_ENABLED,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_hdo_charging_enabled(call):
        def _mutate(item: Dict[str, Any], enabled: bool) -> None:
            charge = item.setdefault("charge", {})
            mode = ensure_mode_entry(charge, MODE_HDO)
            mode["enabled"] = 1 if enabled else 0

        await _handle_device_type_4_settings_enabled_service(
            call,
            service_name=SERVICE_SET_DEVICE_TYPE_4_HDO_CHARGING_ENABLED,
            mutator=_mutate,
        )

    async def handle_set_device_type_4_trigger_phase(call):
        phase = _parse_trigger_phase(call.data.get("phase"))
        az_ids = _resolve_az_device_ids_from_call(call)

        _LOGGER.debug(
            "Service %s called for AZ devices=%s phase=%s",
            SERVICE_SET_DEVICE_TYPE_4_TRIGGER_PHASE,
            az_ids,
            phase,
        )

        for az_device_id in az_ids:
            await client.async_set_device_type_4_trigger_phase(az_device_id, phase)

        await coordinator.async_request_refresh()

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

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING,
            handle_set_device_type_4_block_charging,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_PRIORITIZE_WHEN_CONNECTED):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_PRIORITIZE_WHEN_CONNECTED,
            handle_set_device_type_4_prioritize_when_connected,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_BLOCK_SOLAR_CHARGING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_BLOCK_SOLAR_CHARGING,
            handle_set_device_type_4_block_solar_charging,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING_FROM_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING_FROM_BATTERY,
            handle_set_device_type_4_block_charging_from_battery,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_ALLOW_SOLAR_CHARGING_ONLY_IN_TIME_WINDOW):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_ALLOW_SOLAR_CHARGING_ONLY_IN_TIME_WINDOW,
            handle_set_device_type_4_allow_solar_charging_only_in_time_window,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_TRIGGER_PHASE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_TRIGGER_PHASE,
            handle_set_device_type_4_trigger_phase,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_APPLY_ONLY_IF_CLOUD_IS_OFFLINE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_APPLY_ONLY_IF_CLOUD_IS_OFFLINE,
            handle_set_device_type_4_apply_only_if_cloud_is_offline,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_TIME_WINDOW_CHARGING_ENABLED):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_TIME_WINDOW_CHARGING_ENABLED,
            handle_set_device_type_4_time_window_charging_enabled,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_HDO_CHARGING_ENABLED):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEVICE_TYPE_4_HDO_CHARGING_ENABLED,
            handle_set_device_type_4_hdo_charging_enabled,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEVICE_TYPE_4_MANUAL_POWER):
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
        # If no more entries for this integration exist, remove services
        remaining_entries = hass.config_entries.async_entries(DOMAIN)
        if len(remaining_entries) <= 1:
            try:
                hass.services.async_remove(DOMAIN, SERVICE_SET_MASTER_BOOST)
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_BOOST)
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_KEEP_HEATED)
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_1_BLOCK_SOLAR_HEATING
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_1_BLOCK_HEATING_FROM_BATTERY
                )
                hass.services.async_remove(
                    DOMAIN,
                    SERVICE_SET_DEVICE_TYPE_1_ALLOW_SOLAR_HEATING_ONLY_IN_TIME_WINDOW,
                )
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_BOOST_MODE)
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_1_CONNECTED_PHASE
                )
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_MAX_POWER)
                hass.services.async_remove(DOMAIN, SERVICE_SET_DEVICE_TYPE_1_TEMPS)
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_PRIORITIZE_WHEN_CONNECTED
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_BLOCK_SOLAR_CHARGING
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_BLOCK_CHARGING_FROM_BATTERY
                )
                hass.services.async_remove(
                    DOMAIN,
                    SERVICE_SET_DEVICE_TYPE_4_ALLOW_SOLAR_CHARGING_ONLY_IN_TIME_WINDOW,
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_TRIGGER_PHASE
                )
                hass.services.async_remove(
                    DOMAIN,
                    SERVICE_SET_DEVICE_TYPE_4_APPLY_ONLY_IF_CLOUD_IS_OFFLINE,
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_TIME_WINDOW_CHARGING_ENABLED
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_HDO_CHARGING_ENABLED
                )
                hass.services.async_remove(
                    DOMAIN, SERVICE_SET_DEVICE_TYPE_4_MANUAL_POWER
                )
            except Exception:
                _LOGGER.debug("Failed to remove services during unload")
    return unload_ok

# End Of File
