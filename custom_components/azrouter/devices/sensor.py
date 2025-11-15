# custom_components/azrouter/devices/sensor.py
# -----------------------------------------------------------
# Společné entity pro zařízení (device-level senzory)
# - DeviceBase: nadstavba nad BaseEntity
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
    """Společný základ pro všechny device senzory (deviceType_1, deviceType_4, ...)."""

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
    ):
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
        self._device_id = common.get("id")  # budeme podle toho hledat v coordinator.data["devices"]
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

    def _read_raw(self):
        """
        Najde a vrátí hodnotu z coordinator.data["devices"]
        podle self.device_id a self._raw_path.
        """

        data = self.coordinator.data or {}
        devices = data.get("devices") or []

        # najdeme zařízení podle ID
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

        # parse path např. "power.output.0"
        parts = self._raw_path.split(".")
        cur = dev
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
    """Společný základ pro master senzory (hlavní AZ Router)."""

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
    ):
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
        """Device registry entry pro master jednotku."""
        ident = f"{self._entry.entry_id}_master"

        return DeviceInfo(
            identifiers={(DOMAIN, ident)},
            name="_Master_",
            manufacturer="A-Z Traders",
            model="A-Z Router Smart master",
        )

    def _read_raw(self) -> Any:
        """Čte hodnotu z coordinator.data podle self._raw_path."""
        payload = getattr(self.coordinator, "data", None)
        if payload is None:
            return None
        return _get_value(payload, self._raw_path)

# End Of File
