from __future__ import annotations

from typing import Any, Dict, List
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .devices.device_type_1.select import create_device_type_1_select_entities
from .devices.device_type_4.select import create_device_type_4_select_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AZ Router select entities from a config entry."""
    runtime_data = entry.runtime_data
    if runtime_data is None:
        _LOGGER.debug("select: runtime_data missing for entry %s", entry.entry_id)
        async_add_entities([], True)
        return

    client = runtime_data.client
    coordinator = runtime_data.coordinator
    devices_list: List[Dict[str, Any]] = (
        coordinator.data.get("devices") if coordinator.data else []
    ) or []

    entities = []
    entities.extend(
        create_device_type_1_select_entities(
            client=client,
            coordinator=coordinator,
            entry=entry,
            devices=devices_list,
        )
    )
    entities.extend(
        create_device_type_4_select_entities(
            client=client,
            coordinator=coordinator,
            entry=entry,
            devices=devices_list,
        )
    )
    if entities:
        async_add_entities(entities, True)
