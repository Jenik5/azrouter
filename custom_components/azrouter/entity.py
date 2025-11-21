# custom_components/azrouter/entity.py
# -----------------------------------------------------------
# Base entity class for all AZ Router sensors, numbers, switches.
#
# - BaseEntity: common Home Assistant entity wrapper with device_info,
#               unique_id management, entity_category, unit, and class.
#
# This module also re-exports helper functions from devices/helpers.py.
# -----------------------------------------------------------

from __future__ import annotations
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN
from .devices.helpers import _dig, _get_value  # re-exported helpers for backward compatibility


class BaseEntity(CoordinatorEntity):
    """Shared base entity for AZ Router entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        unit: Optional[Any] = None,
        devclass: Optional[Any] = None,
        device_key: str = "",
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._device_key = device_key

        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if devclass is not None:
            self._attr_device_class = devclass
        if entity_category is not None:
            self._attr_entity_category = entity_category

        # state_class for sensors - concrete classes set this if needed
        self._state_class = None

    @property
    def device_info(self) -> DeviceInfo:
        mac = None
        try:
            mac = self.coordinator.hass.data[DOMAIN][self._entry.entry_id].get("mac")
        except Exception:
            pass

        ident = f"{self._entry.entry_id}"
        if self._device_key:
            ident = f"{self._entry.entry_id}_{self._device_key}"

        info: DeviceInfo = {
            "identifiers": {(DOMAIN, ident)},
            "manufacturer": "A-Z Traders",
            "name": "A-Z Router" + (f" - {self._device_key.capitalize()}" if self._device_key else ""),
            "model": "A-Z Router Smart",
        }
        if mac:
            info["connections"] = {("mac", mac)}
        return info
# End Of File
