# custom_components/azrouter/sensor.py (shim, robust imports inside setup)
from __future__ import annotations
from typing import Any, List, Dict
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
_LOG_TAG = "AZR/sensor"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Platform setup shim for AZ Router sensors.

    - import master handler and device handlers inside setup for reliable logging
    - call master handler to create master-level entities
    - iterate devices list (from hass.data) and call device-specific handlers per instance
    - fall back to generic device handler when specialized file missing
    """
    _LOGGER.debug("%s: async_setup_entry start (entry_id=%s)", _LOG_TAG, entry.entry_id)

    # Basic defensive checks
    entry_data = hass.data.get(DOMAIN)
    if not entry_data:
        _LOGGER.debug("%s: hass.data[%s] missing", _LOG_TAG, DOMAIN)
        async_add_entities([], True)
        return

    bucket = entry_data.get(entry.entry_id)
    if not bucket:
        _LOGGER.debug("%s: no bucket for entry_id %s", _LOG_TAG, entry.entry_id)
        async_add_entities([], True)
        return

    coordinator = bucket.get("coordinator")
    if coordinator is None:
        _LOGGER.debug("%s: coordinator missing for entry %s", _LOG_TAG, entry.entry_id)
        async_add_entities([], True)
        return

    # 1) create master-level sensors
    entities: List[Any] = []
    if master_sensor is None:
        _LOGGER.error("%s: master sensor handler not available -> no master entities created", _LOG_TAG)
    else:
        try:
            created = await master_sensor.async_create_entities(coordinator, entry)
            if isinstance(created, list):
                entities.extend(created)
                _LOGGER.debug("%s: master_sensor created %d entities", _LOG_TAG, len(created))
            else:
                _LOGGER.warning("%s: master_sensor.async_create_entities returned non-list (%s)", _LOG_TAG, type(created))
        except Exception as exc:
            _LOGGER.exception("%s: exception while creating master entities: %s", _LOG_TAG, exc)

    # 2) create device-level sensors from hass.data (if present)
    devices_list = bucket.get("devices") or bucket.get("devices_list") or []
    if not isinstance(devices_list, (list, tuple)):
        devices_list = []

    _LOGGER.debug("%s: creating device sensors for %d devices", _LOG_TAG, len(devices_list))

    for dev in devices_list:
        try:
            if not isinstance(dev, dict):
                _LOGGER.debug("%s: skipping non-dict device entry: %s", _LOG_TAG, repr(dev))
                continue
            dtype = str(dev.get("deviceType", "")).strip()
            common = dev.get("common", {}) or {}
            dev_name = common.get("name", f"device-{common.get('id','?')}")
            _LOGGER.debug("%s: processing device type=%s name=%s", _LOG_TAG, dtype, dev_name)

            created_for_device: List[Any] = []

            if dtype == "1" and device_type_1_sensor is not None:
                try:
                    created_for_device = await device_type_1_sensor.async_create_device_entities(coordinator, entry, dev)
                    _LOGGER.debug("%s: device_type_1 created %d entities for %s", _LOG_TAG, len(created_for_device), dev_name)
                except Exception as exc:
                    _LOGGER.exception("%s: device_type_1 handler failed for %s: %s", _LOG_TAG, dev_name, exc)

            elif dtype == "4" and device_type_4_sensor is not None:
                try:
                    created_for_device = await device_type_4_sensor.async_create_device_entities(coordinator, entry, dev)
                    _LOGGER.debug("%s: device_type_4 created %d entities for %s", _LOG_TAG, len(created_for_device), dev_name)
                except Exception as exc:
                    _LOGGER.exception("%s: device_type_4 handler failed for %s: %s", _LOG_TAG, dev_name, exc)

            elif dtype == "5" and device_type_5_sensor is not None:
                try:
                    created_for_device = await device_type_5_sensor.async_create_device_entities(coordinator, entry, dev)
                    _LOGGER.debug("%s: device_type_5 created %d entities for %s", _LOG_TAG, len(created_for_device), dev_name)
                except Exception as exc:
                    _LOGGER.exception("%s: device_type_5 handler failed for %s: %s", _LOG_TAG, dev_name, exc)

            else:
                # handler missing or unknown type -> try generic fallback if available
                if generic_device is not None:
                    try:
                        created_for_device = await generic_device.async_create_device_entities(coordinator, entry, dev)
                        _LOGGER.debug("%s: generic device handler created %d entities for %s (type=%s)", _LOG_TAG, len(created_for_device), dev_name, dtype)
                    except Exception as exc:
                        _LOGGER.exception("%s: generic device handler failed for %s: %s", _LOG_TAG, dev_name, exc)
                else:
                    _LOGGER.debug("%s: no handler available for device %s (type=%s) and generic not present", _LOG_TAG, dev_name, dtype)

            if created_for_device:
                entities.extend(created_for_device)
            else:
                _LOGGER.debug("%s: no entities created for device %s (type=%s)", _LOG_TAG, dev_name, dtype)

        except Exception as exc:
            _LOGGER.exception("%s: unexpected error while processing device: %s", _LOG_TAG, exc)

    # final add (always call, even with empty list)
    try:
        _LOGGER.debug("%s: calling async_add_entities (count=%d)", _LOG_TAG, len(entities))
        async_add_entities(entities or [], True)
    except Exception as exc:
        _LOGGER.exception("%s: async_add_entities failed: %s", _LOG_TAG, exc)

    _LOGGER.debug("%s: async_setup_entry finished", _LOG_TAG)
