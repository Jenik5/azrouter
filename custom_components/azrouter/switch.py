# custom_components/azrouter/switch.py
# -----------------------------------------------------------
# Switch platform entry point for the AZ Router integration.
#
# - Creates master-level switch entities (e.g. Master Boost)
# - Creates per-device switch entities for known device types
# - Can be extended in the future to support additional types
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, List, Dict
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

from .devices.master import switch as master_switch
from .devices.device_type_1 import switch as dev_type_1_switch
from .devices.device_type_4 import switch as dev_type_4_switch

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AZ Router switches from a config entry."""
    _LOGGER.debug("switch.async_setup_entry start (entry_id=%s)", entry.entry_id)

    runtime_data = entry.runtime_data
    if runtime_data is None:
        _LOGGER.debug("switch: runtime_data missing for entry %s", entry.entry_id)
        async_add_entities([], True)
        return

    coordinator = runtime_data.coordinator
    client = runtime_data.client
    devices: List[Dict[str, Any]] = (
        coordinator.data.get("devices") if coordinator.data else []
    ) or []
    if not isinstance(devices, (list, tuple)):
        _LOGGER.debug("switch: devices is not a list/tuple -> ignoring")
        devices = []

    entities: List[Any] = []

    try:
        _migrate_boiler_switch_names(hass, entry, devices)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("switch: name migration skipped due to error: %s", exc)

    # -----------------------------------------------------------------------
    # Master switches
    # -----------------------------------------------------------------------
    try:
        master_entities: List[Any] = await master_switch.async_create_entities(
            coordinator,
            entry,
            client,
        )
        if master_entities:
            entities.extend(master_entities)
            _LOGGER.debug(
                "switch: created %d master switch entities",
                len(master_entities),
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("switch: failed to create master entities: %s", exc)

    # -----------------------------------------------------------------------
    # Device switches (deviceType 1, 4, ...)
    # -----------------------------------------------------------------------
    _LOGGER.debug("switch: creating device switches for %d devices", len(devices))

    for dev in devices:
        try:
            if not isinstance(dev, dict):
                _LOGGER.debug("switch: skipping non-dict device entry: %r", dev)
                continue

            dev_type = str(dev.get("deviceType", "")).strip()
            common = dev.get("common", {}) or {}
            dev_id = common.get("id")
            dev_name = common.get("name", f"device-{dev_id}")

            created_for_device: List[Any] = []

            if dev_type == "1":
                # Boiler – device_type_1
                try:
                    created_for_device = await dev_type_1_switch.async_create_device_entities(
                        coordinator,
                        entry,
                        client,
                        dev,
                    )
                    _LOGGER.debug(
                        "switch: created %d switch entities for deviceType=1 (id=%s, name=%s)",
                        len(created_for_device),
                        dev_id,
                        dev_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.exception(
                        "switch: failed to create switches for deviceType=1 (id=%s, name=%s): %s",
                        dev_id,
                        dev_name,
                        exc,
                    )

            elif dev_type == "4":
                # Charger – device_type_4
                try:
                    created_for_device = await dev_type_4_switch.async_create_device_entities(
                        coordinator,
                        entry,
                        client,
                        dev,
                    )
                    _LOGGER.debug(
                        "switch: created %d switch entities for deviceType=4 (id=%s, name=%s)",
                        len(created_for_device),
                        dev_id,
                        dev_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.exception(
                        "switch: failed to create switches for deviceType=4 (id=%s, name=%s): %s",
                        dev_id,
                        dev_name,
                        exc,
                    )

            else:
                _LOGGER.debug(
                    "switch: no device switch factory for deviceType=%s (id=%s, name=%s)",
                    dev_type,
                    dev_id,
                    dev_name,
                )

            if created_for_device:
                entities.extend(created_for_device)

        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception(
                "switch: unexpected error while processing device switches: %s",
                exc,
            )

    # -----------------------------------------------------------------------
    # Register all entities
    # -----------------------------------------------------------------------
    try:
        _LOGGER.debug("switch: calling async_add_entities (count=%d)", len(entities))
        async_add_entities(entities or [], True)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("switch: async_add_entities failed: %s", exc)

    _LOGGER.debug("switch.async_setup_entry finished for entry_id=%s", entry.entry_id)


def _migrate_boiler_switch_names(
    hass: HomeAssistant,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> None:
    """Apply one-time name migration for existing device_type_1 switch entities."""
    ent_reg = er.async_get(hass)
    if not hasattr(ent_reg, "async_get_entity_id"):
        # Compatibility guard for HA versions with different registry API shape.
        return
    host = str(entry.data.get("host", "")).strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    router_id = host.rstrip("/")

    key_to_name = {
        "power_boost": "Boost",
        "power_connected_phase_1": "1.1 Connected L1",
        "power_connected_phase_2": "1.2 Connected L2",
        "power_connected_phase_3": "1.3 Connected L3",
        "power_ignore_cycle": "3.1 Keep Heated",
        "power_block_solar_heating": "3.2 Block Solar Heating",
        "power_block_heating_from_battery": "3.3 Block Heating From Battery",
        "power_allowed_solar_time_enabled": "3.4 Allow Solar Heating Only In Time Window",
        "power_offline_only": "4.1 Apply Only If Cloud Is Offline",
    }

    for dev in devices:
        if str(dev.get("deviceType", "")) != "1":
            continue
        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        if dev_id is None:
            continue
        for key, target_name in key_to_name.items():
            unique_id = f"{router_id}_device_1_{dev_id}_{key}"
            entity_id = ent_reg.async_get_entity_id("switch", "azrouter", unique_id)
            if not entity_id:
                continue
            entry_obj = ent_reg.async_get(entity_id)
            if entry_obj is None:
                continue
            if entry_obj.name == target_name:
                continue
            try:
                ent_reg.async_update_entity(entity_id, name=target_name)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "switch: entity name migration failed for %s -> %s: %s",
                    entity_id,
                    target_name,
                    exc,
                )
# End Of File
