# custom_components/azrouter/devices/device_type_1/switch.py
# -----------------------------------------------------------
# Switch entities for device_type_1 (boiler device).
#
# - async_create_device_entities:
#     Creates a boost switch if power.boost is present in the device payload.
#
# - AzRouterDeviceType1BoostSwitch:
#     Boiler boost switch based on DeviceBoostSwitch.
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ...const import MODEL_DEVICE_TYPE_1
from ..switch import DeviceBoostSwitch

_LOGGER = logging.getLogger(__name__)

MODEL_NAME = MODEL_DEVICE_TYPE_1


async def async_create_device_entities(
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    client: AzRouterClient,
    device: Dict[str, Any],
) -> List[SwitchEntity]:
    """Create switch entities for a device_type_1 (boiler) device."""
    entities: List[SwitchEntity] = []

    common = device.get("common", {}) or {}
    dev_id = common.get("id")
    dev_name = common.get("name", f"device-{dev_id}")

    power = device.get("power", {}) or {}
    if "boost" in power:
        _LOGGER.debug(
            "device_type_1.switch: creating Boost switch for id=%s name=%s",
            dev_id,
            dev_name,
        )
        entities.append(
            AzRouterDeviceType1BoostSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                key="power_boost",
                name=f"{dev_name} Boost",
                raw_path="power.boost",
            )
        )

    return entities


class AzRouterDeviceType1BoostSwitch(DeviceBoostSwitch):
    """Boost switch for device_type_1 (boiler)."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        key: str,
        name: str,
        raw_path: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            client=client,
            device=device,
            key=key,
            name=name,
            raw_path=raw_path,
            model=MODEL_NAME,
        )
# End Of File
