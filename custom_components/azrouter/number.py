from __future__ import annotations

from typing import List, Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .api import AzRouterClient

from .devices.master.number import create_master_numbers
from .devices.device_type_1.number import create_device_type_1_numbers


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

    # --- DEVICE_TYPE_1 NUMBER ENTITIES (bojler) ---
    entities.extend(
        create_device_type_1_numbers(
            client=client,
            coordinator=coordinator,
            entry=entry,
            devices=devices_list,
        )
    )

    if entities:
        async_add_entities(entities, True)
