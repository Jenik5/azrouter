# custom_components/azrouter/number.py
# -----------------------------------------------------------
# Main number platform:
# - creates master number entities
# - creates device_type_1 number entities
# - creates device_type_4 number entities
# - exposes service helpers for __init__.py
# -----------------------------------------------------------

from __future__ import annotations

from typing import List, Any, Dict
import logging
import copy

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError


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

    runtime_data = entry.runtime_data
    if runtime_data is None:
        _LOGGER.debug("number: runtime_data missing for entry %s", entry.entry_id)
        async_add_entities([], True)
        return

    client: AzRouterClient = runtime_data.client
    coordinator = runtime_data.coordinator
    devices_list: List[Dict[str, Any]] = (
        coordinator.data.get("devices") if coordinator.data else []
    ) or []

    try:
        _migrate_wallbox_number_names(hass, entry, devices_list)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("number: wallbox number name migration skipped: %s", exc)

    entities: List[Any] = []

    # --- MASTER NUMBER ENTITIES ---
    entities.extend(
        create_master_numbers(
            client=client,
            coordinator=coordinator,
            entry=entry,
        )
    )

    # --- DEVICE_TYPE_1 NUMBER ENTITIES ---
    entities.extend(
        create_device_type_1_numbers(
            client=client,
            coordinator=coordinator,
            entry=entry,
            devices=devices_list,
        )
    )

    # --- DEVICE_TYPE_4 NUMBER ENTITIES ---
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


def _migrate_wallbox_number_names(
    hass: HomeAssistant,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> None:
    ent_reg = er.async_get(hass)
    if not hasattr(ent_reg, "async_get_entity_id"):
        return

    host = str(entry.data.get("host", "")).strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    router_id = host.rstrip("/")

    key_to_name = {
        "charge_manual_power": "7.1 Manual Charging Power",
    }

    for dev in devices:
        if str(dev.get("deviceType", "")) != "4":
            continue
        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        if dev_id is None:
            continue
        for key, target_name in key_to_name.items():
            unique_id = f"{router_id}_device_4_{dev_id}_{key}"
            entity_id = ent_reg.async_get_entity_id("number", "azrouter", unique_id)
            if not entity_id:
                continue
            entry_obj = ent_reg.async_get(entity_id)
            if entry_obj is None or entry_obj.name == target_name:
                continue
            try:
                ent_reg.async_update_entity(entity_id, name=target_name)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "number: wallbox entity name migration failed for %s -> %s: %s",
                    entity_id,
                    target_name,
                    exc,
                )


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
        raise ServiceValidationError(
            f"Missing max_power for device {device_id}."
        )

    # clamp to valid range
    try:
        value = int(max_power)
    except Exception:
        raise ServiceValidationError(
            f"Invalid max_power '{max_power}' for device {device_id}."
        )

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
        raise ServiceValidationError(
            f"Device {device_id} not found in coordinator data."
        )

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
        raise HomeAssistantError(
            f"Failed to write max power for device {device_id}: {exc}"
        ) from exc


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
        raise ServiceValidationError(
            f"Device {device_id} not found in coordinator data."
        )

    # work on a copy so we don't mutate coordinator.data in place
    settings_src = root.get("settings") or []
    if not isinstance(settings_src, list) or not settings_src:
        raise ServiceValidationError(
            f"No settings found for device {device_id}."
        )

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
        raise HomeAssistantError(
            f"Failed to write temperatures for device {device_id}: {exc}"
        ) from exc

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
        mode_list = charge_settings.get("mode")

        if not isinstance(mode_list, list):
            mode_list = []
            charge_settings["mode"] = mode_list

        manual_mode = None
        for mode in mode_list:
            try:
                if int(mode.get("id", -1)) == 1:
                    manual_mode = mode
                    break
            except Exception:
                continue

        if manual_mode is None:
            manual_mode = {"id": 1}
            mode_list.append(manual_mode)

        manual_mode["enabled"] = 1
        manual_mode["power"] = int(value)
        changed = True

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
