from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import time
import asyncio
import copy
import logging
from time import monotonic

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError

from ...api import AzRouterClient
from ...const import MODEL_DEVICE_TYPE_1
from ..sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_1 = "1"
MINUTES_MIN = 0
MINUTES_MAX = 1439


def create_device_type_1_time_entities(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[TimeEntity]:
    entities: List[TimeEntity] = []
    for dev in devices:
        if str(dev.get("deviceType", "")) != DEVICE_TYPE_1:
            continue
        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        if dev_id is None:
            continue

        if _has_allowed_solar_time(dev, "start"):
            entities.append(
                DeviceType1AllowedSolarHeatingStartTime(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    key="allowed_solar_heating_start_time",
                    name="3.4.1 Window Start",
                )
            )
        if _has_allowed_solar_time(dev, "stop"):
            entities.append(
                DeviceType1AllowedSolarHeatingStopTime(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    key="allowed_solar_heating_stop_time",
                    name="3.4.2 Window Stop",
                )
            )

        for idx in range(3):
            if _has_boost_window_time(dev, idx, "start"):
                entities.append(
                    DeviceType1BoostWindowStartTime(
                        coordinator=coordinator,
                        entry=entry,
                        client=client,
                        device=dev,
                        device_id=int(dev_id),
                        window_index=idx,
                        key=f"boost_window_{idx+1}_start",
                        name=f"4.{idx+3}.2 Boost Window {idx+1} Start",
                    )
                )
            if _has_boost_window_time(dev, idx, "stop"):
                entities.append(
                    DeviceType1BoostWindowStopTime(
                        coordinator=coordinator,
                        entry=entry,
                        client=client,
                        device=dev,
                        device_id=int(dev_id),
                        window_index=idx,
                        key=f"boost_window_{idx+1}_stop",
                        name=f"4.{idx+3}.3 Boost Window {idx+1} Stop",
                    )
                )
    return entities


def _has_allowed_solar_time(device: Dict[str, Any], key: str) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        power = (item or {}).get("power", {}) or {}
        allowed = power.get("allowed_solar_heating_time", {}) or {}
        if key in allowed:
            return True
    return False


def _has_boost_window_time(device: Dict[str, Any], index: int, key: str) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        boost = (item or {}).get("boost", {}) or {}
        windows = boost.get("windows") or []
        if not isinstance(windows, list) or len(windows) <= index:
            continue
        window = windows[index] or {}
        if isinstance(window, dict) and key in window:
            return True
    return False


class DeviceType1AllowedSolarHeatingTimeBase(DeviceBase, TimeEntity):
    _OPTIMISTIC_WINDOW = 8.0
    _REFRESH_DELAY = 4.5
    _setting_key: str = ""

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        device_id: int,
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path=f"settings.0.power.allowed_solar_heating_time.{self._setting_key}",
            unit=None,
            devclass=None,
            icon="mdi:clock-outline",
            entity_category=EntityCategory.CONFIG,
            model=MODEL_DEVICE_TYPE_1,
        )
        self._client = client
        self._device_id = int(device_id)
        self._device_type = DEVICE_TYPE_1
        self._optimistic_value: Optional[time] = None
        self._optimistic_until: float = 0.0

    def _find_device_from_coordinator(self) -> Optional[Dict[str, Any]]:
        data = self.coordinator.data or {}
        devices = data.get("devices") or []
        for dev in devices:
            try:
                if (
                    str(dev.get("deviceType")) == self._device_type
                    and int(dev.get("common", {}).get("id", -1)) == self._device_id
                ):
                    return dev
            except Exception:
                continue
        return None

    def _read_minutes(self) -> Optional[int]:
        dev = self._find_device_from_coordinator()
        if not dev:
            return None
        settings = dev.get("settings") or []
        if not isinstance(settings, list) or not settings:
            return None
        allowed = (
            (settings[0].get("power") or {}).get("allowed_solar_heating_time", {}) or {}
        )
        value = allowed.get(self._setting_key)
        if isinstance(value, (int, float)):
            ivalue = int(value)
            return max(MINUTES_MIN, min(MINUTES_MAX, ivalue))
        return None

    def _read_enabled(self) -> Optional[bool]:
        dev = self._find_device_from_coordinator()
        if not dev:
            return None
        settings = dev.get("settings") or []
        if not isinstance(settings, list) or not settings:
            return None
        allowed = (
            (settings[0].get("power") or {}).get("allowed_solar_heating_time", {}) or {}
        )
        enabled = allowed.get("enabled")
        if isinstance(enabled, bool):
            return enabled
        if isinstance(enabled, (int, float)):
            return int(enabled) != 0
        return None

    @property
    def available(self) -> bool:
        enabled = self._read_enabled()
        return super().available and enabled is True

    @staticmethod
    def _to_time(minutes: int) -> time:
        return time(hour=minutes // 60, minute=minutes % 60)

    @staticmethod
    def _to_minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    @property
    def native_value(self) -> Optional[time]:
        if self._optimistic_value is not None and monotonic() < self._optimistic_until:
            return self._optimistic_value
        minutes = self._read_minutes()
        return None if minutes is None else self._to_time(minutes)

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_value is not None:
            current = self._read_minutes()
            now = monotonic()
            if (
                current is not None
                and self._optimistic_value == self._to_time(current)
            ) or now >= self._optimistic_until:
                self._optimistic_value = None
                self._optimistic_until = 0.0
        super()._handle_coordinator_update()

    async def async_set_value(self, value: time) -> None:
        enabled = self._read_enabled()
        if enabled is not True:
            raise HomeAssistantError(
                "Solar heating window time is available only when "
                "'Allow Solar Heating Only In Time Window' is enabled."
            )

        minutes = max(MINUTES_MIN, min(MINUTES_MAX, self._to_minutes(value)))
        self._optimistic_value = self._to_time(minutes)
        self._optimistic_until = monotonic() + self._OPTIMISTIC_WINDOW
        self.async_write_ha_state()

        dev = self._find_device_from_coordinator()
        if not dev:
            self._optimistic_value = None
            self._optimistic_until = 0.0
            raise HomeAssistantError("Device not found in coordinator data.")

        payload = copy.deepcopy(dev)
        settings = payload.get("settings") or []
        if not isinstance(settings, list) or not settings:
            self._optimistic_value = None
            self._optimistic_until = 0.0
            raise HomeAssistantError("Device has no settings section.")

        for item in settings:
            power = item.setdefault("power", {})
            allowed = power.setdefault("allowed_solar_heating_time", {})
            allowed[self._setting_key] = int(minutes)

        await self._client.async_post_device_settings(payload)
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()


class DeviceType1AllowedSolarHeatingStartTime(DeviceType1AllowedSolarHeatingTimeBase):
    _setting_key = "start"


class DeviceType1AllowedSolarHeatingStopTime(DeviceType1AllowedSolarHeatingTimeBase):
    _setting_key = "stop"


class DeviceType1BoostWindowTimeBase(DeviceBase, TimeEntity):
    _OPTIMISTIC_WINDOW = 8.0
    _REFRESH_DELAY = 4.5
    _setting_key: str = ""

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        device_id: int,
        window_index: int,
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path=f"settings.0.boost.windows.{window_index}.{self._setting_key}",
            unit=None,
            devclass=None,
            icon="mdi:calendar-clock",
            entity_category=EntityCategory.CONFIG,
            model=MODEL_DEVICE_TYPE_1,
        )
        self._client = client
        self._device_id = int(device_id)
        self._device_type = DEVICE_TYPE_1
        self._window_index = int(window_index)
        self._optimistic_value: Optional[time] = None
        self._optimistic_until: float = 0.0

    def _find_device_from_coordinator(self) -> Optional[Dict[str, Any]]:
        data = self.coordinator.data or {}
        devices = data.get("devices") or []
        for dev in devices:
            try:
                if (
                    str(dev.get("deviceType")) == self._device_type
                    and int(dev.get("common", {}).get("id", -1)) == self._device_id
                ):
                    return dev
            except Exception:
                continue
        return None

    def _read_boost_mode(self) -> Optional[int]:
        dev = self._find_device_from_coordinator()
        if not dev:
            return None
        settings = dev.get("settings") or []
        if not isinstance(settings, list) or not settings:
            return None
        mode = ((settings[0].get("boost") or {}).get("mode"))
        if isinstance(mode, (int, float)):
            return int(mode)
        return None

    @property
    def available(self) -> bool:
        mode = self._read_boost_mode()
        return super().available and mode in (2, 3)

    def _read_minutes(self) -> Optional[int]:
        dev = self._find_device_from_coordinator()
        if not dev:
            return None
        settings = dev.get("settings") or []
        if not isinstance(settings, list) or not settings:
            return None
        boost = settings[0].get("boost", {}) or {}
        windows = boost.get("windows") or []
        if not isinstance(windows, list) or len(windows) <= self._window_index:
            return None
        window = windows[self._window_index] or {}
        if not isinstance(window, dict):
            return None
        value = window.get(self._setting_key)
        if isinstance(value, (int, float)):
            ivalue = int(value)
            return max(MINUTES_MIN, min(MINUTES_MAX, ivalue))
        return None

    @staticmethod
    def _to_time(minutes: int) -> time:
        return time(hour=minutes // 60, minute=minutes % 60)

    @staticmethod
    def _to_minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    @property
    def native_value(self) -> Optional[time]:
        if self._optimistic_value is not None and monotonic() < self._optimistic_until:
            return self._optimistic_value
        minutes = self._read_minutes()
        return None if minutes is None else self._to_time(minutes)

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_value is not None:
            current = self._read_minutes()
            now = monotonic()
            if (
                current is not None
                and self._optimistic_value == self._to_time(current)
            ) or now >= self._optimistic_until:
                self._optimistic_value = None
                self._optimistic_until = 0.0
        super()._handle_coordinator_update()

    async def async_set_value(self, value: time) -> None:
        mode = self._read_boost_mode()
        if mode not in (2, 3):
            raise HomeAssistantError("Boost windows are available only in window/window+hdo mode.")

        minutes = max(MINUTES_MIN, min(MINUTES_MAX, self._to_minutes(value)))
        self._optimistic_value = self._to_time(minutes)
        self._optimistic_until = monotonic() + self._OPTIMISTIC_WINDOW
        self.async_write_ha_state()

        dev = self._find_device_from_coordinator()
        if not dev:
            self._optimistic_value = None
            self._optimistic_until = 0.0
            raise HomeAssistantError("Device not found in coordinator data.")

        payload = copy.deepcopy(dev)
        settings = payload.get("settings") or []
        if not isinstance(settings, list) or not settings:
            self._optimistic_value = None
            self._optimistic_until = 0.0
            raise HomeAssistantError("Device has no settings section.")

        for item in settings:
            boost = item.setdefault("boost", {})
            windows = boost.setdefault("windows", [])
            while len(windows) <= self._window_index:
                windows.append({"enabled": 0, "start": 0, "stop": 0})
            window = windows[self._window_index]
            if not isinstance(window, dict):
                window = {}
                windows[self._window_index] = window
            window[self._setting_key] = int(minutes)

        await self._client.async_post_device_settings(payload)
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()


class DeviceType1BoostWindowStartTime(DeviceType1BoostWindowTimeBase):
    _setting_key = "start"


class DeviceType1BoostWindowStopTime(DeviceType1BoostWindowTimeBase):
    _setting_key = "stop"
