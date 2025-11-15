# custom_components/azrouter/entity.py
from __future__ import annotations
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN


def _dig(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _get_value(payload: Dict[str, Any], path: str) -> Any:
    """Try to get a value from payload, checking top-level, status, and power roots."""
    if not isinstance(payload, dict):
        return None
    # 1) top-level
    v = _dig(payload, path)
    if v is not None:
        return v
    # 2) payload['status']
    status_root = payload.get("status") if isinstance(payload, dict) else None
    if isinstance(status_root, dict):
        v = _dig(status_root, path)
        if v is not None:
            return v
    # 3) payload['power']
    power_root = payload.get("power") if isinstance(payload, dict) else None
    if isinstance(power_root, dict):
        v = _dig(power_root, path)
        if v is not None:
            return v
    return None


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
        entity_category: EntityCategory | None = None,  # ← nový parametr
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._device_key = device_key

        # optional unit / device class
        #if unit is not None:
        #    self._unit = unit
        #if devclass is not None:
        #    self._devclass = devclass

        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if devclass is not None:
            self._attr_device_class = devclass
        if entity_category is not None:
            self._attr_entity_category = entity_category  # ← tady se to propsne do HA

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
