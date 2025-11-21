# custom_components/azrouter/devices/device_generic/sensor.py
# -----------------------------------------------------------
# Generic device sensor handler.
#
# - Works with the "common" section of any device payload.
# - Creates basic sensors for common.* fields (name, status, type, etc.).
# - Used as a fallback for any deviceType (1, 4, 5, ...).
# - Builds on DeviceBase from devices/sensor.py.
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfSoundPressure
from homeassistant.helpers.entity import EntityCategory

from ...const import (
    MODEL_DEVICE_GENERIC,
    DEVICE_STATUS_STRINGS,
    DEVICE_TYPE_STRINGS,
)
from ..sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Factory: create entities for any device with a "common" section
# ---------------------------------------------------------------------------

async def async_create_device_entities(
    coordinator,
    entry: ConfigEntry,
    device: Dict[str, Any],
) -> List[SensorEntity]:
    """
    Create generic device entities based on the 'common' section.

    entry:  ConfigEntry (entry_id is used as "router serial" in DeviceBase)
    device: JSON dict describing the device (common, power/charge, settings, ...)
    """
    entities: List[SensorEntity] = []

    flat = _flatten_device(device)
    _LOGGER.debug(
        "device_generic: flattened device paths: %s",
        [p for p, _ in flat],
    )

    common = device.get("common", {}) or {}
    dev_name = common.get("name", f"device-{common.get('id', '?')}")
    dev_type = device.get("deviceType", "?")

    for path, value in flat:
        # We do not expose ".id" paths as entities
        if path.endswith(".id"):
            continue

        # Generic handler only cares about common.*
        if not path.startswith("common."):
            continue

        match path:
            # -------------------------------------------------------
            # common.name  -> string
            # -------------------------------------------------------
            case "common.name":
                entities.append(
                    DeviceStringSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_name",
                        name="Name",
                        device=device,
                        raw_path=path,
                    )
                )

            # -------------------------------------------------------
            # common.priority  -> numeric (priority/order)
            # -------------------------------------------------------
            case "common.priority":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_priority",
                        name="Priority",
                        device=device,
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # -------------------------------------------------------
            # common.status  -> numeric (device status)
            # -------------------------------------------------------
            case "common.status":
                entities.append(
                    DeviceMappedSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_status",
                        name="Status",
                        device=device,
                        raw_path=path,
                        mapping=DEVICE_STATUS_STRINGS,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # -------------------------------------------------------
            # common.signal  -> numeric (signal strength, typically dBm)
            # -------------------------------------------------------
            case "common.signal":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_signal",
                        name="WiFi Signal",
                        device=device,
                        raw_path=path,
                        unit=UnitOfSoundPressure.DECIBEL,
                        devclass=SensorDeviceClass.SIGNAL_STRENGTH,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # -------------------------------------------------------
            # common.type  -> numeric (device type)
            # -------------------------------------------------------
            case "common.type":
                entities.append(
                    DeviceMappedSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_type",
                        name="Device Type",
                        device=device,
                        raw_path=path,
                        mapping=DEVICE_TYPE_STRINGS,
                    )
                )

            # -------------------------------------------------------
            # common.sn  -> string (serial number)
            # -------------------------------------------------------
            case "common.sn":
                entities.append(
                    DeviceStringSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_sn",
                        name="Serial Number",
                        device=device,
                        raw_path=path,
                    )
                )

            # -------------------------------------------------------
            # common.fw  -> string (firmware)
            # -------------------------------------------------------
            case "common.fw":
                entities.append(
                    DeviceStringSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_fw",
                        name="FW Version",
                        device=device,
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # -------------------------------------------------------
            # common.hw  -> numeric or string (HW revision)
            # -------------------------------------------------------
            case "common.hw":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="common_hw",
                        name="HW Version",
                        device=device,
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # -------------------------------------------------------
            # Anything else under common.* is logged for now
            # -------------------------------------------------------
            case _:
                _LOGGER.debug(
                    "device_generic: unhandled common path %s = %s (type=%s)",
                    path,
                    value,
                    type(value).__name__,
                )

    _LOGGER.debug(
        "device_generic: created %d entities for device %s (type=%s, id=%s)",
        len(entities),
        dev_name,
        dev_type,
        common.get("id", "unknown"),
    )

    return entities


# ---------------------------------------------------------------------------
# Helper: flatten device dict into (path, value) pairs
# ---------------------------------------------------------------------------

def _flatten_device(d: Dict[str, Any], prefix: str = "") -> List[Tuple[str, Any]]:
    """Recursively flatten a device JSON structure into (path, value) pairs."""
    out: List[Tuple[str, Any]] = []

    if isinstance(d, dict):
        for k, v in d.items():
            new_prefix = f"{prefix}.{k}" if prefix else k
            out.extend(_flatten_device(v, new_prefix))
    elif isinstance(d, list):
        for idx, item in enumerate(d):
            new_prefix = f"{prefix}.{idx}"
            out.extend(_flatten_device(item, new_prefix))
    else:
        out.append((prefix, d))

    return out


# ---------------------------------------------------------------------------
# Sensor entity classes
# ---------------------------------------------------------------------------

class DeviceStringSensor(DeviceBase, SensorEntity):
    """String sensor based on a JSON path in the device payload."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        device: Dict[str, Any],
        raw_path: str,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path=raw_path,
            unit=None,
            devclass=None,
            icon=icon,
            entity_category=entity_category,
            model=MODEL_DEVICE_GENERIC,
        )

    @property
    def native_value(self):
        value = self._read_raw()
        return None if value is None else str(value)


class DeviceNumericSensor(DeviceBase, SensorEntity):
    """Numeric sensor based on a JSON path in the device payload."""

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
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path=raw_path,
            unit=unit,
            devclass=devclass,
            icon=icon,
            entity_category=entity_category,
            model=MODEL_DEVICE_GENERIC,
        )

    @property
    def native_value(self):
        raw = self._read_raw()
        if raw is None:
            return None

        # Convert string to numeric if possible
        if isinstance(raw, str):
            s = raw.strip()
            if s == "" or s.lower() in ("n/a", "na", "none", "-"):
                return None
            try:
                raw = float(s) if "." in s else int(s)
            except Exception:
                return None

        try:
            val = float(raw)
            if abs(val - int(val)) < 1e-9:
                return int(round(val))
            return val
        except Exception:
            _LOGGER.exception(
                "DeviceNumericSensor: failed to parse numeric value for %s (raw=%r, path=%s)",
                getattr(self, "_attr_unique_id", "?"),
                raw,
                self._raw_path,
            )
            return None


class DeviceMappedSensor(DeviceBase, SensorEntity):
    """Sensor that maps a numeric code to a string using a provided mapping list."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        device: Dict[str, Any],
        raw_path: str,
        mapping: List[str],
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        # For mapped states we do not want a unit or device_class
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path=raw_path,
            unit=None,
            devclass=None,
            icon=icon,
            entity_category=entity_category,
            model=MODEL_DEVICE_GENERIC,
        )
        self._mapping = mapping

    @property
    def native_value(self):
        raw = self._read_raw()
        if raw is None:
            return None

        # Try to obtain an integer index
        if isinstance(raw, str):
            s = raw.strip()
            if s == "":
                return None
            try:
                raw = int(s)
            except Exception:
                _LOGGER.debug(
                    "DeviceMappedSensor: non-integer raw value %r for %s",
                    raw,
                    getattr(self, "_attr_unique_id", "?"),
                )
                return None

        try:
            idx = int(raw)
        except Exception:
            _LOGGER.debug(
                "DeviceMappedSensor: cannot cast %r to int for %s",
                raw,
                getattr(self, "_attr_unique_id", "?"),
            )
            return None

        if 0 <= idx < len(self._mapping):
            return self._mapping[idx]

        # If index is out of range, return a readable fallback
        return f"unknown({idx})"
# End Of File
