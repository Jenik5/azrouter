# custom_components/azrouter/devices/device_type_4/switch.py
# -----------------------------------------------------------
# Switch entities for device_type_4 (charger device).
#
# - async_create_device_entities:
#     Creates a boost switch if charge.boost is present in the device payload.
#
# - AzRouterDeviceType4BoostSwitch:
#     Charger boost switch based on DeviceBoostSwitch.
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..switch import DeviceBoostSwitch

_LOGGER = logging.getLogger(__name__)

MODEL_NAME = "AZ Charger Cube"  # adjust if needed


async def async_create_device_entities(
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    client: AzRouterClient,
    device: Dict[str, Any],
) -> List[SwitchEntity]:
    """Create switch entities for a device_type_4 (charger) device."""
    entities: List[SwitchEntity] = []

    common = device.get("common", {}) or {}
    dev_id = common.get("id")
    dev_name = common.get("name", f"device-{dev_id}")

    charge = device.get("charge", {}) or {}
    if "boost" in charge:
        _LOGGER.debug(
            "device_type_4.switch: creating Boost switch for id=%s name=%s",
            dev_id,
            dev_name,
        )
        entities.append(
            AzRouterDeviceType4BoostSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                key="charge_boost",
                name=f"{dev_name} Boost",
                raw_path="charge.boost",
            )
        )

    return entities


class AzRouterDeviceType4BoostSwitch(DeviceBoostSwitch):
    """Boost switch for device_type_4 (charger)."""

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
