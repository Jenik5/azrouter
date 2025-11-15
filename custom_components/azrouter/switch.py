from __future__ import annotations
from typing import Any, List, Dict
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .devices.master import switch as master_switch  # master factory

# nové importy pro devices
from .devices.device_type_1 import switch as dev_type_1_switch
from .devices.device_type_4 import switch as dev_type_4_switch

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not data:
        _LOGGER.debug("azrouter.switch: no data for entry %s", entry.entry_id)
        return

    coordinator = data["coordinator"]
    client = data.get("client")
    devices: List[Dict[str, Any]] = data.get("devices", []) or []

    all_entities: List[Any] = []

    # --- MASTER switche ---
    try:
        master_entities: List[Any] = await master_switch.async_create_entities(
            coordinator, entry, client
        )
        if master_entities:
            all_entities.extend(master_entities)
            _LOGGER.debug(
                "azrouter.switch: added %d entities from master.switch",
                len(master_entities),
            )
    except Exception as exc:
        _LOGGER.exception(
            "azrouter.switch: failed to create master entities: %s", exc
        )

    # --- DEVICE switche (deviceType 1, 4, ...) ---
    for dev in devices:
        dev_type = str(dev.get("deviceType", ""))
        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        dev_name = common.get("name", f"device-{dev_id}")

        try:
            if dev_type == "1":
                # Bojler – device_type_1
                ents = await dev_type_1_switch.async_create_device_entities(
                    coordinator, entry, client, dev
                )
                if ents:
                    all_entities.extend(ents)
                    _LOGGER.debug(
                        "azrouter.switch: added %d switch entities for deviceType=1 (id=%s, name=%s)",
                        len(ents),
                        dev_id,
                        dev_name,
                    )

            elif dev_type == "4":
                # Charger – device_type_4
                ents = await dev_type_4_switch.async_create_device_entities(
                    coordinator, entry, client, dev
                )
                if ents:
                    all_entities.extend(ents)
                    _LOGGER.debug(
                        "azrouter.switch: added %d switch entities for deviceType=4 (id=%s, name=%s)",
                        len(ents),
                        dev_id,
                        dev_name,
                    )

            else:
                _LOGGER.debug(
                    "azrouter.switch: no switch factory for deviceType=%s (id=%s, name=%s)",
                    dev_type,
                    dev_id,
                    dev_name,
                )

        except Exception as exc:
            _LOGGER.exception(
                "azrouter.switch: failed to create switch entities for deviceType=%s (id=%s, name=%s): %s",
                dev_type,
                dev_id,
                dev_name,
                exc,
            )

    # --- registrace všech entit ---
    if all_entities:
        async_add_entities(all_entities, True)
        _LOGGER.debug(
            "azrouter.switch: added total %d switch entities", len(all_entities)
        )
    else:
        _LOGGER.debug("azrouter.switch: no switch entities created")
