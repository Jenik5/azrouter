# custom_components/azrouter/sensor.py
from __future__ import annotations
from typing import Any, List
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .devices.master import sensor as master_sensor
from .devices.device_type_1 import sensor as device_type_1_sensor
from .devices.device_type_4 import sensor as device_type_4_sensor
from .devices.device_type_5 import sensor as device_type_5_sensor
from .devices.device_generic import sensor as device_generic_sensor


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AZ Router sensors from a config entry.

    This function:
        - creates master-level sensor entities,
        - creates per-device sensor entities for known device types,
        - uses a generic device handler as a fallback for unknown types.
    """
    _LOGGER.debug("async_setup_entry start (entry_id=%s)", entry.entry_id)

    entry_data = hass.data.get(DOMAIN)
    if not entry_data:
        _LOGGER.debug("hass.data[%s] missing", DOMAIN)
        async_add_entities([], True)
        return

    bucket = entry_data.get(entry.entry_id)
    if not bucket:
        _LOGGER.debug("no bucket for entry_id %s", entry.entry_id)
        async_add_entities([], True)
        return

    coordinator = bucket.get("coordinator")
    if coordinator is None:
        _LOGGER.debug("coordinator missing for entry %s", entry.entry_id)
        async_add_entities([], True)
        return

    entities: List[Any] = []

    # 1) master-level sensors
    try:
        created = await master_sensor.async_create_entities(coordinator, entry)
        if isinstance(created, list):
            entities.extend(created)
            _LOGGER.debug("master sensor handler created %d entities", len(created))
        else:
            _LOGGER.warning(
                "master_sensor.async_create_entities returned non-list (%s)",
                type(created),
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("exception while creating master entities: %s", exc)

    # 2) device-level sensors
    devices_list = bucket.get("devices") or bucket.get("devices_list") or []
    if not isinstance(devices_list, (list, tuple)):
        _LOGGER.debug("devices_list is not a list/tuple -> ignoring")
        devices_list = []

    _LOGGER.debug("creating device sensors for %d devices", len(devices_list))

    for dev in devices_list:
        try:
            if not isinstance(dev, dict):
                _LOGGER.debug("skipping non-dict device entry: %r", dev)
                continue

            dtype = str(dev.get("deviceType", "")).strip()
            common = dev.get("common") or {}
            dev_name = common.get("name", f"device-{common.get('id', '?')}")
            _LOGGER.debug("processing device type=%s name=%s", dtype, dev_name)

            created_for_device: List[Any] = []

            if dtype == "1":
                try:
                    created_for_device = await device_type_1_sensor.async_create_device_entities(
                        coordinator,
                        entry,
                        dev,
                    )
                    _LOGGER.debug(
                        "device_type_1 handler created %d entities for %s",
                        len(created_for_device),
                        dev_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.exception(
                        "device_type_1 handler failed for %s: %s",
                        dev_name,
                        exc,
                    )

            elif dtype == "4":
                try:
                    created_for_device = await device_type_4_sensor.async_create_device_entities(
                        coordinator,
                        entry,
                        dev,
                    )
                    _LOGGER.debug(
                        "device_type_4 handler created %d entities for %s",
                        len(created_for_device),
                        dev_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.exception(
                        "device_type_4 handler failed for %s: %s",
                        dev_name,
                        exc,
                    )

            elif dtype == "5":
                try:
                    created_for_device = await device_type_5_sensor.async_create_device_entities(
                        coordinator,
                        entry,
                        dev,
                    )
                    _LOGGER.debug(
                        "device_type_5 handler created %d entities for %s",
                        len(created_for_device),
                        dev_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.exception(
                        "device_type_5 handler failed for %s: %s",
                        dev_name,
                        exc,
                    )

            else:
                # handler missing or unknown type -> try generic fallback
                try:
                    created_for_device = await device_generic_sensor.async_create_device_entities(
                        coordinator,
                        entry,
                        dev,
                    )
                    _LOGGER.debug(
                        "generic device handler created %d entities for %s (type=%s)",
                        len(created_for_device),
                        dev_name,
                        dtype,
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.exception(
                        "generic device handler failed for %s (type=%s): %s",
                        dev_name,
                        dtype,
                        exc,
                    )

            if created_for_device:
                entities.extend(created_for_device)
            else:
                _LOGGER.debug(
                    "no entities created for device %s (type=%s)",
                    dev_name,
                    dtype,
                )

        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("unexpected error while processing device: %s", exc)

    # 3) final add
    try:
        _LOGGER.debug("calling async_add_entities (count=%d)", len(entities))
        async_add_entities(entities or [], True)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("async_add_entities failed: %s", exc)

    _LOGGER.debug("async_setup_entry finished for entry_id=%s", entry.entry_id)
# End Of File
