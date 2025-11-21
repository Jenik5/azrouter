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

from .const import DOMAIN
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

    entry_data = hass.data.get(DOMAIN)
    if not entry_data:
        _LOGGER.debug("switch: hass.data[%s] missing", DOMAIN)
        async_add_entities([], True)
        return

    bucket = entry_data.get(entry.entry_id)
    if not bucket:
        _LOGGER.debug("switch: no bucket for entry_id %s", entry.entry_id)
        async_add_entities([], True)
        return

    coordinator = bucket.get("coordinator")
    if coordinator is None:
        _LOGGER.debug("switch: coordinator missing for entry %s", entry.entry_id)
        async_add_entities([], True)
        return

    client = bucket.get("client")
    devices: List[Dict[str, Any]] = bucket.get("devices", []) or []
    if not isinstance(devices, (list, tuple)):
        _LOGGER.debug("switch: devices is not a list/tuple -> ignoring")
        devices = []

    entities: List[Any] = []

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
# End Of File
