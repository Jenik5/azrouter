# custom_components/azrouter/devices/sensor.py
# -----------------------------------------------------------
# Shared entity base classes for device-level and master sensors.
#
# - DeviceBase:
#     Base for sensors bound to a specific device (deviceType_1, deviceType_4, ...)
#
# - MasterBase:
#     Base for sensors and switches bound to the master AZ Router unit.
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict
import logging
from types import SimpleNamespace

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory

from ..const import DOMAIN
from ..entity import BaseEntity, _get_value

_LOGGER = logging.getLogger(__name__)


class DeviceBase(BaseEntity):
    """Shared base for all device-level sensors."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        device: Dict[str, Any],
        raw_path: str,
        unit: str | None = None,
        devclass: SensorDeviceClass | None = None,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            unit=unit,
            devclass=devclass,
            device_key="",
            entity_category=entity_category,
        )

        self._device = device
        self._raw_path = raw_path
        self._device_model_override = model

        if icon is not None:
            self._attr_icon = icon

        common = device.get("common", {}) if isinstance(device, dict) else {}
        self._device_id = common.get("id")
        self._router = SimpleNamespace(
            serial_number=entry.entry_id,
        )
        self._device_cfg = SimpleNamespace(
            id=common.get("id"),
            name=common.get("name", f"device-{common.get('id', '?')}"),
            type=common.get("type"),
        )

        dev_id = self._device_cfg.id
        if dev_id is not None:
            self._attr_unique_id = f"{entry.entry_id}_device_{dev_id}_{key}"
        else:
            self._attr_unique_id = f"{entry.entry_id}_device_X_{key}"

        from homeassistant.util import slugify

        name_slug = slugify(self._device_cfg.name or f"device_{dev_id}")
        dev_id_str = str(dev_id) if dev_id is not None else "X"
        object_id = f"{name_slug}_id_{dev_id_str}_{key}"
        self.entity_id = f"sensor.{object_id}"

    @property
    def router(self):
        return self._router

    @property
    def device_cfg(self):
        return self._device_cfg

    @property
    def device_info(self) -> DeviceInfo:
        if self._device_model_override:
            model = self._device_model_override
        else:
            raw_type = self._device_cfg.type
            model = f"Device type {raw_type}" if raw_type is not None else "Device"

        return DeviceInfo(
            identifiers={
                (DOMAIN, f"{self._router.serial_number}_device_{self._device_cfg.id}")
            },
            name=self._device_cfg.name,
            manufacturer="A-Z Traders",
            model=model,
        )

    def _read_raw(self) -> Any:
        """Find and return a value from coordinator.data['devices'] for this device."""
        data = self.coordinator.data or {}
        devices = data.get("devices") or []

        dev = None
        for d in devices:
            try:
                cid = d.get("common", {}).get("id")
                if cid == self._device_id:
                    dev = d
                    break
            except Exception:
                continue

        if dev is None:
            return None

        parts = self._raw_path.split(".")
        cur: Any = dev
        try:
            for p in parts:
                if isinstance(cur, list):
                    cur = cur[int(p)]
                else:
                    cur = cur[p]
            return cur
        except Exception:
            return None


class MasterBase(BaseEntity):
    """Shared base for master-level sensors and switches."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        raw_path: str,
        unit: str | None = None,
        devclass: SensorDeviceClass | None = None,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            unit=unit,
            devclass=devclass,
            device_key="master",
            entity_category=entity_category,
        )

        self._raw_path = raw_path

        if icon is not None:
            self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        """Device registry entry for the master unit."""
        ident = f"{self._entry.entry_id}_master"

        return DeviceInfo(
            identifiers={(DOMAIN, ident)},
            name="_Master_",
            manufacturer="A-Z Traders",
            model="A-Z Router Smart master",
        )

    def _read_raw(self) -> Any:
        """Read a value for this master entity based on self._raw_path.

        Supports:
        - flattened list in coordinator.data["master_data"] (path/value pairs),
        - structured lookup via _get_value(...) as a fallback.
        """
        data = getattr(self.coordinator, "data", None)
        if not data:
            return None

        # Preferred: flattened master_data list
        master = data.get("master_data")
        if isinstance(master, list):
            for item in master:
                try:
                    if item.get("path") == self._raw_path:
                        return item.get("value")
                except Exception:
                    continue

        # Fallback: try structured lookup in the root payload
        try:
            return _get_value(data, self._raw_path)
        except Exception:
            return None
# End Of File
