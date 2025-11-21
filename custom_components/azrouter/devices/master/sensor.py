# custom_components/azrouter/devices/master/sensor.py
# -----------------------------------------------------------
# Master-level sensor entities for the AZ Router integration.
#
# - async_create_entities: factory that builds all master sensors
# - AzRouterScalarSensor: scalar/text master sensor (grid, cloud, status)
# - AzRouterBinarySensor: binary master sensor (flags like HDO)
# - AzRouterTimestampSensor: timestamp master sensor (system time, last update)
# -----------------------------------------------------------

from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone
import logging
import re

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.const import (
    UnitOfPower,
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfTemperature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as hass_dt

from ..sensor import MasterBase

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Human-friendly string maps
# ---------------------------------------------------------------------------

MODE_STRINGS = ["Summer", "Winter"]
SYSTEM_STATUS_STRINGS = ["Online", "Offline", "Updating"]
HDO_STRINGS = ["Off", "On"]
CLOUD_STRINGS = ["No", "Yes"]
GRID_STRINGS = ["Connected", "Disconnected"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_master_value(master_data: list[dict], raw_path: str):
    """Return value from master_data for the given path, or None."""
    for item in master_data:
        if item.get("path") == raw_path:
            return item.get("value")
    return None


# ---------------------------------------------------------------------------
# Factory: create master entities
# ---------------------------------------------------------------------------

async def async_create_entities(coordinator, entry: ConfigEntry) -> List[SensorEntity]:
    """
    Create master sensors based on the flattened list in coordinator.data["master_data"].

    master_data is expected to be:
        [
            {"path": "power.input.voltage.0.value", "value": ...},
            {"path": "status.system.status", "value": ...},
            ...
        ]
    """
    entities: list[SensorEntity] = []

    master = coordinator.data.get("master_data", [])
    if not isinstance(master, list):
        _LOGGER.warning("master_data is not a list (%s)", type(master))
        return []

    for item in master:
        path = item.get("path")

        if not isinstance(path, str):
            continue

        # Skip ".id" fields, they are not exposed as entities
        if path.endswith(".id"):
            continue

        # --- Input voltages: power.input.voltage.<idx>.value ---
        m = re.match(r"^power\.input\.voltage\.(\d+)\.value$", path)
        if m:
            idx = int(m.group(1))
            if idx > 2:
                continue
            entities.append(
                AzRouterScalarSensor(
                    coordinator=coordinator,
                    entry=entry,
                    key=f"input_voltage_{idx}",
                    name=f"Grid Voltage L{idx+1}",
                    raw_path=path,
                    unit=UnitOfElectricPotential.VOLT,
                    devclass=SensorDeviceClass.VOLTAGE,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )
            continue

        # --- Input currents: power.input.current.<idx>.value ---
        m = re.match(r"^power\.input\.current\.(\d+)\.value$", path)
        if m:
            idx = int(m.group(1))
            if idx > 2:
                continue
            entities.append(
                AzRouterScalarSensor(
                    coordinator=coordinator,
                    entry=entry,
                    key=f"input_current_{idx}",
                    name=f"Grid Current L{idx+1}",
                    raw_path=path,
                    unit=UnitOfElectricCurrent.AMPERE,
                    devclass=SensorDeviceClass.CURRENT,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )
            continue

        # --- Input power per phase: power.input.power.<idx>.value ---
        m = re.match(r"^power\.input\.power\.(\d+)\.value$", path)
        if m:
            idx = int(m.group(1))
            if idx > 2:
                continue

            entities.append(
                AzRouterScalarSensor(
                    coordinator=coordinator,
                    entry=entry,
                    key=f"input_power_{idx}",
                    name=f"Grid Power L{idx+1}",
                    raw_path=path,
                    unit=UnitOfPower.WATT,
                    devclass=SensorDeviceClass.POWER,
                )
            )

            # When we see L3 (idx == 2) also create a total power sensor.
            if idx == 2:
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="input_power_total",
                        name="Grid Power Total",
                        raw_path="power.input.power.total",  # special raw_path handled by the class
                        unit=UnitOfPower.WATT,
                        devclass=SensorDeviceClass.POWER,
                    )
                )
            continue

        # --- Input status (connected/disconnected) per phase ---
        m = re.match(r"^power\.input\.status\.(\d+)\.value$", path)
        if m:
            idx = int(m.group(1))
            if idx > 2:
                continue
            entities.append(
                AzRouterScalarSensor(
                    coordinator=coordinator,
                    entry=entry,
                    key=f"input_status_{idx}",
                    name=f"Grid Status L{idx+1}",
                    raw_path=path,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )
            continue

        # --- Output power per phase: power.output.power.<idx>.value ---
        m = re.match(r"^power\.output\.power\.(\d+)\.value$", path)
        if m:
            idx = int(m.group(1))
            if idx < 3:
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key=f"output_power_{idx}",
                        name=f"Routed Power L{idx+1}",
                        raw_path=path,
                        unit=UnitOfPower.WATT,
                        devclass=SensorDeviceClass.POWER,
                    )
                )
                continue

            # idx == 3 -> Routed total
            if idx == 3:
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="output_power_total",
                        name="Routed Power Total",
                        raw_path=path,
                        unit=UnitOfPower.WATT,
                        devclass=SensorDeviceClass.POWER,
                    )
                )
                continue

        # --- Remaining single-value paths handled by match/case ---
        match path:
            case "power.output.energy.0.value":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="output_energy_0",
                        name="Saved Energy Total",
                        raw_path=path,
                        unit=UnitOfEnergy.KILO_WATT_HOUR,
                        devclass=SensorDeviceClass.ENERGY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "power.output.energy.1.value":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="output_energy_1",
                        name="Saved Energy This Year",
                        raw_path=path,
                        unit=UnitOfEnergy.KILO_WATT_HOUR,
                        devclass=SensorDeviceClass.ENERGY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "power.output.energy.2.value":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="output_energy_2",
                        name="Saved Energy This Month",
                        raw_path=path,
                        unit=UnitOfEnergy.KILO_WATT_HOUR,
                        devclass=SensorDeviceClass.ENERGY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "power.output.energy.3.value":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="output_energy_3",
                        name="Saved Energy This Week",
                        raw_path=path,
                        unit=UnitOfEnergy.KILO_WATT_HOUR,
                        devclass=SensorDeviceClass.ENERGY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "power.output.energy.4.value":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="output_energy_4",
                        name="Saved Energy Today",
                        raw_path=path,
                        unit=UnitOfEnergy.KILO_WATT_HOUR,
                        devclass=SensorDeviceClass.ENERGY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "power.lastUpdate":
                entities.append(
                    AzRouterTimestampSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="last_update_ts",
                        name="Last Update",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.status":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="system_status",
                        name="System Status",
                        raw_path=path,
                    )
                )
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="system_status_code",
                        name="System Status Code",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.hdo":
                entities.append(
                    AzRouterBinarySensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="system_hdo",
                        name="HDO",
                        raw_path=path,
                    )
                )
                continue

            case "status.system.mode":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="mode",
                        name="Mode",
                        raw_path=path,
                    )
                )
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="mode_code",
                        name="Mode Code",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.temperature":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="system_temperature",
                        name="System Temperature",
                        raw_path=path,
                        unit=UnitOfTemperature.CELSIUS,
                        devclass=SensorDeviceClass.TEMPERATURE,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.time":
                entities.append(
                    AzRouterTimestampSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="system_time",
                        name="System Time",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.masterBoost":
                # handled by switches, no sensor
                continue

            case "status.system.uptime":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="system_uptime",
                        name="System Uptime",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.hw":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="hw_version",
                        name="HW Version",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.sn":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="serial_number",
                        name="Serial Number",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.mac":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="system_mac",
                        name="MAC Address",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.fw":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="fw_version",
                        name="FW Version",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.system.www":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="web_ui",
                        name="Web UI",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.cloud.status":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="cloud_status",
                        name="Cloud Status",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.cloud.reachable":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="cloud_reachable",
                        name="Cloud Reachable",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.cloud.registered":
                entities.append(
                    AzRouterScalarSensor(
                        coordinator=coordinator,
                        entry=entry,
                        key="cloud_registered",
                        name="Cloud Registered",
                        raw_path=path,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                )
                continue

            case "status.activeDevice.id":
                continue
            case "status.activeDevice.maxPower":
                continue
            case "status.activeDevice.name":
                continue

            case _:
                _LOGGER.debug("Unhandled master path %s = %s", path, item.get("value"))
                continue

    return entities


# ---------------------------------------------------------------------------
# Entity classes – based on MasterBase
# ---------------------------------------------------------------------------

class AzRouterScalarSensor(MasterBase, SensorEntity):
    """
    Generic numeric/text master sensor.

    Reads a value from coordinator.data["master_data"] based on self._raw_path and
    applies per-key transformations (scaling, mapping, formatting).
    """

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        raw_path: str,
        unit=None,
        devclass=None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            raw_path=raw_path,
            unit=unit,
            devclass=devclass,
            entity_category=entity_category,
        )

        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if devclass is not None:
            self._attr_device_class = devclass

        self._raw_path = raw_path
        self._key = key

        # UI details – icons
        if self._key.startswith("cloud_"):
            self._attr_icon = "mdi:cloud"
        if self._key == "system_uptime":
            self._attr_icon = "mdi:clock"

    @property
    def native_value(self):
        """
        Read value from master_data and apply key-specific transformations:

          - scale voltages/currents (mV/mA → V/A),
          - map status codes to strings,
          - format MAC address,
          - convert uptime seconds to human-readable string.
        """
        data = self.coordinator.data or {}
        master = data.get("master_data", [])

        # Special case: aggregated input power from all phases
        if self._raw_path == "power.input.power.total":
            total = 0
            for item in master:
                p = item.get("path")
                if not isinstance(p, str):
                    continue
                if p.startswith("power.input.power.") and p.endswith(".value"):
                    try:
                        total += item.get("value", 0) or 0
                    except Exception:
                        continue
            return total

        val = _get_master_value(master, self._raw_path)
        if val is None:
            return None

        # transformations/mappings
        if self._key.startswith("input_voltage_"):
            val = round(val / 1000.0, 3)
        if self._key.startswith("input_current_"):
            val = round(val / 1000.0, 3)
        if self._key.startswith("input_status_"):
            try:
                val = GRID_STRINGS[int(val)]
            except Exception:
                pass

        if self._key == "system_status":
            if isinstance(val, int) and 0 <= val < len(SYSTEM_STATUS_STRINGS):
                val = SYSTEM_STATUS_STRINGS[val]

        if self._key == "mode":
            if isinstance(val, int) and 0 <= val < len(MODE_STRINGS):
                val = MODE_STRINGS[val]

        if self._key in ("cloud_reachable", "cloud_registered"):
            if isinstance(val, int) and 0 <= val < len(CLOUD_STRINGS):
                val = CLOUD_STRINGS[val]

        if self._key == "system_mac":
            try:
                mac = str(val).replace("-", "").replace(":", "").strip()
                if len(mac) == 12 and all(c in "0123456789ABCDEFabcdef" for c in mac):
                    mac = mac.upper()
                    return ":".join(mac[i:i + 2] for i in range(0, 12, 2))
                return str(val)
            except Exception:
                return str(val)

        if self._key == "system_uptime":
            try:
                seconds = int(val)
                # In case value is in milliseconds
                if seconds > 10**6:
                    seconds = int(seconds / 1000)
                days, rem = divmod(int(seconds), 86400)
                hours, rem = divmod(rem, 3600)
                minutes, sec = divmod(rem, 60)
                return f"{days} days {hours:02d}:{minutes:02d}:{sec:02d}"
            except Exception:
                return val

        return val


class AzRouterBinarySensor(MasterBase, BinarySensorEntity):
    """Binary master sensor for simple 0/1 flags."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        raw_path: str,
        unit=None,
        devclass=None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            raw_path=raw_path,
            unit=unit,
            devclass=devclass,
            entity_category=entity_category,
        )

        self._raw_path = raw_path

        if devclass is not None:
            self._attr_device_class = devclass

        if self._raw_path == "status.system.hdo":
            self._attr_icon = "mdi:toggle-switch"

    @property
    def is_on(self) -> Optional[bool]:
        """Return boolean state based on the value in master_data."""
        data = self.coordinator.data or {}
        master = data.get("master_data", [])

        val = _get_master_value(master, self._raw_path)
        if val is None:
            return None

        try:
            if isinstance(val, bool):
                return bool(val)
            ival = int(val)
            return ival != 0
        except Exception:
            s = str(val).lower()
            if s in ("on", "true", "yes"):
                return True
            if s in ("off", "false", "no"):
                return False
        return None


class AzRouterTimestampSensor(MasterBase, SensorEntity):
    """
    Timestamp master sensor with robust epoch parsing and conversion to local time.

    Handles:
      - epoch in seconds or milliseconds,
      - potential “local epoch” vs UTC,
      - basic sanity checks on timestamp range.
    """

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        raw_path: str,
        unit=None,
        devclass=None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            raw_path=raw_path,
            unit=unit,
            devclass=devclass,
            entity_category=entity_category,
        )

        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if devclass is not None:
            self._attr_device_class = devclass

        self._raw_path = raw_path

        if self._raw_path in ("status.system.time", "power.lastUpdate"):
            self._attr_icon = "mdi:clock"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        master = data.get("master_data", [])

        raw = _get_master_value(master, self._raw_path)
        if raw is None:
            return None

        if isinstance(raw, str):
            raw = raw.strip()
            if raw == "":
                return None

        try:
            if isinstance(raw, (int, float)):
                ts = int(raw)
            else:
                ts = int(float(raw))
        except Exception as err:
            _LOGGER.debug(
                "TimestampSensor %s: cannot convert raw value to number: %s (%s)",
                self._attr_name,
                raw,
                err,
            )
            return None

        # Detect milliseconds vs seconds
        if ts > 10**12:
            ts = int(ts / 1000)

        # Detect local epoch vs UTC epoch
        try:
            now_utc_ts = int(datetime.now(timezone.utc).timestamp())
            utco = hass_dt.now().utcoffset() or 0
            offset_sec = int(utco.total_seconds()) if hasattr(utco, "total_seconds") else int(utco)
            if abs((ts - now_utc_ts) - offset_sec) <= 120:
                ts = int(ts - offset_sec)
        except Exception as exc:
            _LOGGER.debug(
                "TimestampSensor %s: error while detecting local epoch: %s",
                self._attr_name,
                exc,
            )

        # Sanity check (between year 2000 and 2100)
        if ts < 946684800 or ts > 4102444800:
            return None

        try:
            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_local = hass_dt.as_local(dt_utc)
            return dt_local.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as err:
            _LOGGER.exception(
                "TimestampSensor %s: error converting timestamp: %s",
                self._attr_name,
                err,
            )
            return None
# End Of File
