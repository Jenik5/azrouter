# custom_components/azrouter/number.py
# -----------------------------------------------------------
# Main number platform:
# - creates master number entities
# - creates device_type_1 number entities (boiler)
# - exposes service helpers for __init__.py
# -----------------------------------------------------------

from __future__ import annotations

from typing import List, Any, Dict
import logging
import copy

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError


from .const import DOMAIN
from .api import AzRouterClient

from .devices.master.number import create_master_numbers
from .devices.device_type_1.number import create_device_type_1_numbers
from .devices.device_type_4.number import create_device_type_4_numbers

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AZ Router number entities from a config entry."""

    integration_data = hass.data[DOMAIN][entry.entry_id]

    client: AzRouterClient = integration_data["client"]
    coordinator = integration_data["coordinator"]
    devices_list: List[Dict[str, Any]] = integration_data["devices"]

    entities: List[Any] = []

    # --- MASTER NUMBER ENTITIES ---
    entities.extend(
        create_master_numbers(
            client=client,
            coordinator=coordinator,
            entry=entry,
        )
    )

    # --- DEVICE_TYPE_1 NUMBER ENTITIES (boiler) ---
    entities.extend(
        create_device_type_1_numbers(
            client=client,
            coordinator=coordinator,
            entry=entry,
            devices=devices_list,
        )
    )

    # --- DEVICE_TYPE_4 NUMBER ENTITIES (boiler) ---
    entities.extend(
        create_device_type_4_numbers(
            client=client,
            coordinator=coordinator,
            entry=entry,
            devices=devices_list,
        )
    )

    if entities:
        async_add_entities(entities, True)


# ======================================================================
#  SERVICE HELPERS – used by __init__.py
# ======================================================================

# same limits as in DeviceType1MaxPowerNumber
MIN_MAXPOWER = 100
MAX_MAXPOWER = 3500

# same limits as in DeviceType1TempBase
TEMP_MIN = 20
TEMP_MAX = 85


async def async_service_set_device_type_1_max_power(
    *,
    hass,
    client: AzRouterClient,
    coordinator,
    device_id: int,
    max_power: int | None,
) -> None:
    """Service helper: set power.maxPower for device_type_1."""

    if max_power is None:
        _LOGGER.debug(
            "Service set_device_type_1_max_power ignored for device %s (value is None)",
            device_id,
        )
        return

    # clamp to valid range
    try:
        value = int(max_power)
    except Exception:
        _LOGGER.warning(
            "Service set_device_type_1_max_power: invalid value '%s' for device %s",
            max_power,
            device_id,
        )
        return

    if value < MIN_MAXPOWER:
        value = MIN_MAXPOWER
    if value > MAX_MAXPOWER:
        value = MAX_MAXPOWER

    data = coordinator.data or {}
    devices = data.get("devices") or []

    root: Dict[str, Any] | None = None
    for dev in devices:
        try:
            if (
                str(dev.get("deviceType")) == "1"
                and int(dev.get("common", {}).get("id", -1)) == int(device_id)
            ):
                root = dev
                break
        except Exception:
            continue

    if not root:
        _LOGGER.warning(
            "Service set_device_type_1_max_power: device id=%s not found in coordinator data",
            device_id,
        )
        return

    # build payload similar to DeviceType1MaxPowerNumber
    dev_payload = copy.deepcopy(root)

    # 1) power.maxPower
    power = dev_payload.setdefault("power", {})
    power["maxPower"] = int(value)

    # 2) settings[*].power.max – keep it in sync with maxPower
    settings_list = dev_payload.setdefault("settings", [])
    if not isinstance(settings_list, list):
        settings_list = []
        dev_payload["settings"] = settings_list

    if not settings_list:
        # minimal fallback – two entries (e.g. summer/winter)
        settings_list.extend([{"power": {}}, {"power": {}}])

    for s in settings_list:
        p = s.setdefault("power", {})
        p["max"] = int(value)

    _LOGGER.debug(
        "Service set_device_type_1_max_power: device %s → maxPower=%s",
        device_id,
        value,
    )

    try:
        await client.async_post_device_settings(dev_payload)
    except Exception as exc:
        _LOGGER.error(
            "Service set_device_type_1_max_power: write failed for device %s: %s",
            device_id,
            exc,
        )


async def async_service_set_device_type_1_temperatures(
    *,
    hass,
    client: AzRouterClient,
    coordinator,
    device_id: int,
    target_temperature: int | None,
    boost_temperature: int | None,
) -> None:
    """Service helper: set targetTemperature and/or targetTemperatureBoost."""

    data = coordinator.data or {}
    devices = data.get("devices") or []

    root: Dict[str, Any] | None = None
    for dev in devices:
        try:
            if (
                str(dev.get("deviceType")) == "1"
                and int(dev.get("common", {}).get("id", -1)) == int(device_id)
            ):
                root = dev
                break
        except Exception:
            continue

    if not root:
        _LOGGER.warning(
            "Service set_device_type_1_temperatures: device id=%s not found in coordinator data",
            device_id,
        )
        return

    # work on a copy so we don't mutate coordinator.data in place
    settings_src = root.get("settings") or []
    if not isinstance(settings_src, list) or not settings_src:
        _LOGGER.warning(
            "Service set_device_type_1_temperatures: no settings found for device %s",
            device_id,
        )
        return

    settings_list = copy.deepcopy(settings_src)

    changed = False

    # --- Target Temperature ---
    if target_temperature not in (None, 0):
        try:
            v = int(target_temperature)
        except Exception:
            v = None

        if v is not None:
            if v < TEMP_MIN:
                v = TEMP_MIN
            if v > TEMP_MAX:
                v = TEMP_MAX

            for entry in settings_list:
                power = entry.setdefault("power", {})
                power["targetTemperature"] = v

            _LOGGER.debug(
                "Service set_device_type_1_temperatures: device %s → targetTemperature=%s",
                device_id,
                v,
            )
            changed = True

    # --- Boost Target Temperature ---
    if boost_temperature not in (None, 0):
        try:
            v2 = int(boost_temperature)
        except Exception:
            v2 = None

        if v2 is not None:
            if v2 < TEMP_MIN:
                v2 = TEMP_MIN
            if v2 > TEMP_MAX:
                v2 = TEMP_MAX

            for entry in settings_list:
                power = entry.setdefault("power", {})
                power["targetTemperatureBoost"] = v2

            _LOGGER.debug(
                "Service set_device_type_1_temperatures: device %s → targetTemperatureBoost=%s",
                device_id,
                v2,
            )
            changed = True

    if not changed:
        _LOGGER.debug(
            "Service set_device_type_1_temperatures: no changes for device %s",
            device_id,
        )
        return

    device_payload = {
        "deviceType": "1",
        "common": root.get("common", {"id": device_id}),
        "power": root.get("power", {}),
        "settings": settings_list,
    }

    try:
        await client.async_post_device_settings(device_payload)
    except Exception as exc:
        _LOGGER.error(
            "Service set_device_type_1_temperatures: write failed for device %s: %s",
            device_id,
            exc,
        )

# ----------------------------------------------------------------------
#  SERVICE HELPER – device_type_4 manual charging power (mode id=1)
# ----------------------------------------------------------------------

DEVICE_TYPE_4 = "4"

# Same breaker → max power mapping as in DeviceType4ManualChargingPowerNumber
CB_TO_MAX_POWER = {
    10: 2300,
    16: 3700,
    24: 5500,
    32: 7400,
}
MANUAL_MIN_POWER_W = 1400


async def async_service_set_device_type_4_manual_power(
    *,
    hass,
    client: AzRouterClient,
    coordinator,
    device_id: int,
    manual_power: int | None,
) -> None:
    """Service helper: set manual charging power (mode id=1) for device_type_4."""

    if manual_power is None:
        raise HomeAssistantError(
            "No power value specified for Charger manual power service."
        )

    data = coordinator.data or {}
    devices = data.get("devices") or []

    root: Dict[str, Any] | None = None
    for dev in devices:
        try:
            if (
                str(dev.get("deviceType")) == DEVICE_TYPE_4
                and int(dev.get("common", {}).get("id", -1)) == int(device_id)
            ):
                root = dev
                break
        except Exception:
            continue

    if not root:
        _LOGGER.warning(
            "Service set_device_type_4_manual_power: device id=%s not found in coordinator data",
            device_id,
        )
        raise HomeAssistantError(
            "Selected device is not an AZ Charger (deviceType=4) or is no longer available."
        )

    # optional, když chceš ještě explicitně hlídat deviceType:
    dev_type = str(root.get("deviceType"))
    if dev_type != DEVICE_TYPE_4:
        _LOGGER.warning(
            "Service set_device_type_4_manual_power: device id=%s has deviceType=%s, expected 4",
            device_id,
            dev_type,
        )
        raise HomeAssistantError(
            "This service can only be used with AZ Charger devices (deviceType=4)."
        )

    charge = root.get("charge", {}) or {}
    cb_value = int(charge.get("circuitBreaker", 16))

    max_limit = CB_TO_MAX_POWER.get(cb_value)
    if max_limit is None:
        max_limit = max(CB_TO_MAX_POWER.values())

    try:
        value = int(manual_power)
    except Exception:
        _LOGGER.warning(
            "Service set_device_type_4_manual_power: invalid value '%s' for device %s",
            manual_power,
            device_id,
        )
        raise HomeAssistantError(
            f"Invalid power value '{manual_power}'. Please enter a number in watts."
        )

    # clamp do [MANUAL_MIN_POWER_W, max_limit]
    if value < MANUAL_MIN_POWER_W:
        _LOGGER.debug(
            "Service set_device_type_4_manual_power: requested %s W below minimum, clamped to %s W",
            value,
            MANUAL_MIN_POWER_W,
        )
        value = MANUAL_MIN_POWER_W
    if value > max_limit:
        _LOGGER.debug(
            "Service set_device_type_4_manual_power: requested %s W above max %s W, clamped",
            value,
            max_limit,
        )
        value = max_limit

    dev_payload = copy.deepcopy(root)

    settings_list = dev_payload.get("settings") or []
    if not isinstance(settings_list, list) or not settings_list:
        _LOGGER.warning(
            "Service set_device_type_4_manual_power: no settings found for device %s",
            device_id,
        )
        raise HomeAssistantError(
            "Device has no settings section – cannot update manual charging power."
        )

    changed = False

    for entry in settings_list:
        charge_settings = entry.setdefault("charge", {})
        mode_list = charge_settings.get("mode") or []

        if not isinstance(mode_list, list):
            continue

        for mode in mode_list:
            try:
                if int(mode.get("id", -1)) == 1:
                    mode["power"] = int(value)
                    changed = True
            except Exception:
                continue

    if not changed:
        _LOGGER.debug(
            "Service set_device_type_4_manual_power: no mode id=1 found for device %s",
            device_id,
        )
        raise HomeAssistantError(
            "Device has no manual charging mode (mode id=1), nothing to change."
        )

    _LOGGER.debug(
        "Service set_device_type_4_manual_power: device %s → manualPower=%s (max_limit=%s)",
        device_id,
        value,
        max_limit,
    )

    try:
        await client.async_post_device_settings(dev_payload)
    except Exception as exc:
        _LOGGER.error(
            "Service set_device_type_4_manual_power: write failed for device %s: %s",
            device_id,
            exc,
        )
        raise HomeAssistantError(
            f"Failed to write settings for device {device_id}: {exc}"
        )


# End Of File
