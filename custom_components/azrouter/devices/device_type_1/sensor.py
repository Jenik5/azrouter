# custom_components/azrouter/devices/device_generic/sensor.py
# -----------------------------------------------------------
# Generic device handler
# - pracuje se sekcí "common" v JSONu zařízení
# - vytváří základní senzory pro common.*
# - funguje pro deviceType 1, 4, 5, ... (cokoliv s "common")
# - používá DeviceNumericSensor a DeviceStringSensor z devices/sensor.py
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfSoundPressure, UnitOfPower, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory


from ..sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)
LOG_PREFIX = "AZR/devices/device_type_1"

MODEL_NAME = "A-Z Router Smart slave"

DEVICE_STATUS_STRINGS = ["unpaired", "online", "offline", "error", "active"]
DEVICE_TYPE_STRINGS = ["Generic", "Power", "HDO", "Fire", "Charger", "Inverter"]

# ---------------------------------------------------------------------------
# Factory: vytvoření entit pro libovolné zařízení se sekcí "common"
# ---------------------------------------------------------------------------

async def async_create_device_entities(
    coordinator,
    entry: ConfigEntry,
    device: Dict[str, Any],
) -> List[SensorEntity]:
    """
    Generic device entities based on the 'common' section.

    entry:  ConfigEntry (entry_id používáme jako "router serial" v DeviceBase)
    device: JSON dict se strukturou zařízení (common, power, settings, ...)
    """
    entities: List[SensorEntity] = []

    flat = _flatten_device(device)
    _LOGGER.debug("%s flattened device paths: %s", LOG_PREFIX, [p for p, _ in flat])

    common = device.get("common", {}) or {}
    dev_name = common.get("name", f"device-{common.get('id', '?')}")
    dev_type = device.get("deviceType", "?")

    for path, value in flat:
        # ID pole nechceme jako sensor – stejně jako v původním kódu
        if path.endswith(".id"):
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
            # common.priority  -> číslo (pořadí / priorita)
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
            # common.status  -> číslo (stav zařízení)
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
            # common.signal  -> číslo (síla signálu, typicky dBm)
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
            # common.type  -> číslo (typ zařízení)
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
                        #entity_category=EntityCategory.NONE,
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
            # common.hw  -> číslo nebo string (HW revize)
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
            # POWER.* — deviceType=1 (bojler)
            # -------------------------------------------------------

            # power.output.<idx> – výkon do bojleru po fázích L1–L3
            case p if p.startswith("power.output."):
                try:
                    idx = int(p.split(".")[-1])
                except ValueError:
                    _LOGGER.debug("%s: invalid output index in path %s", LOG_PREFIX, p)
                    continue

                if idx < 0 or idx > 2:
                    # jen L1–L3
                    continue

                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key=f"power_output_l{idx+1}",
                        name=f"{dev_name} Power L{idx+1}",
                        device=device,
                        raw_path=path,
                        unit=UnitOfPower.WATT,
                        devclass=SensorDeviceClass.POWER,
                    )
                )

            # power.totalPower – celkový aktuální výkon
            case "power.totalPower":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="power_total",
                        name=f"{dev_name} Power Total",
                        device=device,
                        raw_path=path,
                        unit=UnitOfPower.WATT,
                        devclass=SensorDeviceClass.POWER,
                    )
                )

            # power.boostSource – zatím jen číslo (diagnostika)
            case "power.boostSource":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="power_boost_source",
                        name=f"{dev_name} Boost Source",
                        device=device,
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # power.boostTempOverride – číslo (diagnostika)
            case "power.boostTempOverride":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="power_boost_temp_override",
                        name=f"{dev_name} Boost Temp Override",
                        device=device,
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # power.temperature – teplota bojleru
            case "power.temperature":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="power_temperature",
                        name=f"{dev_name} Temperature",
                        device=device,
                        raw_path=path,
                        unit=UnitOfTemperature.CELSIUS,
                        devclass=SensorDeviceClass.TEMPERATURE,
                    )
                )

            # power.outletMode – číslo (diagnostika)
            case "power.outletMode":
                entities.append(
                    DeviceNumericSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="power_outlet_mode",
                        name=f"{dev_name} Outlet Mode",
                        device=device,
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )

            # vědomě přeskočíme:
            #   power.boost          -> bude switch
            #   power.maxPower       -> bude number v nastavení
            #   power.connectedPhase -> bude v settings

            # -------------------------------------------------------
            # Všechno ostatní zatím jen zalogujeme
            # -------------------------------------------------------

            case _:
                _LOGGER.debug(
                    "%s generic: unhandled common path %s = %s (type=%s)",
                    LOG_PREFIX,
                    path,
                    value,
                    type(value).__name__,
                )

    _LOGGER.debug(
        "%s created %d generic entities for device %s (type=%s, id=%s)",
        LOG_PREFIX,
        len(entities),
        dev_name,
        dev_type,
        common.get("id", "unknown"),
    )

    return entities


# ---------------------------------------------------------------------------
# Pomocná funkce
# ---------------------------------------------------------------------------

def _flatten_device(d: Dict[str, Any], prefix: str = "") -> List[Tuple[str, Any]]:
    """Rekurzivně zploští JSON do dvojic (path, value)."""
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
# Sensory
# ---------------------------------------------------------------------------

class DeviceStringSensor(DeviceBase, SensorEntity):
    """Textový senzor založený na JSON path."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        device: Dict[str, Any],
        raw_path: str,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,  # ← nový parametr
    ):
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
            entity_category=entity_category,  # ← pošleme dál
            model=MODEL_NAME,
        )

        
    @property
    def native_value(self):
        v = self._read_raw()
        return None if v is None else str(v)


class DeviceNumericSensor(DeviceBase, SensorEntity):
    """Číselný senzor založený na JSON path."""

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
        entity_category: EntityCategory | None = None,  # ← nový parametr
    ):
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
            entity_category=entity_category,  # ← pošleme dál
            model=MODEL_NAME,
        )

    @property
    def native_value(self):
        v = self._read_raw()
        if v is None:
            return None

        # převod string → číslo (podobně jako v původním kódu)
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in ("n/a", "na", "none", "-"):
                return None
            try:
                v = float(s) if "." in s else int(s)
            except Exception:
                return None

        try:
            val = float(v)
            if abs(val - int(val)) < 1e-9:
                return int(round(val))
            return val
        except Exception:
            _LOGGER.exception(
                "DeviceNumericSensor: Failed to parse numeric value for %s (raw=%r, path=%s)",
                getattr(self, "_attr_unique_id", "?"),
                v,
                self._raw_path,
            )
            return None

class DeviceMappedSensor(DeviceBase, SensorEntity):
    """Senzor, který mapuje číselný stav na text podle předané mapy."""

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
    ):
        # u mapovaných stavů nechceme jednotku ani device_class
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
            model=MODEL_NAME,
        )
        self._mapping = mapping

    @property
    def native_value(self):
        v = self._read_raw()
        if v is None:
            return None

        # pokusíme se získat integer index
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return None
            try:
                v = int(s)
            except Exception:
                _LOGGER.debug(
                    "%s DeviceMappedSensor: non-integer raw value %r for %s",
                    LOG_PREFIX,
                    v,
                    getattr(self, "_attr_unique_id", "?"),
                )
                return None

        try:
            idx = int(v)
        except Exception:
            _LOGGER.debug(
                "%s DeviceMappedSensor: cannot cast %r to int for %s",
                LOG_PREFIX,
                v,
                getattr(self, "_attr_unique_id", "?"),
            )
            return None

        if 0 <= idx < len(self._mapping):
            return self._mapping[idx]

        # mimo rozsah – vrátíme něco rozumného
        return f"unknown({idx})"

# End Of File
