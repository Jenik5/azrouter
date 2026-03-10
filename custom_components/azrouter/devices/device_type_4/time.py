from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import time
import asyncio
import copy
from time import monotonic

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..sensor import DeviceBase
from .helpers import (
    DEVICE_TYPE_4,
    MINUTES_MAX,
    MINUTES_MIN,
    MODE_TIME_WINDOW,
    MODEL_NAME,
    ensure_charge_settings_list,
    ensure_mode_entry,
    ensure_window_entry,
    find_device_from_coordinator,
    has_charge_section,
    has_charge_setting,
    has_mode_window_setting,
    is_block_charging_enabled,
    is_block_solar_charging_enabled,
    read_charge_setting,
    read_mode_enabled,
    read_mode_window_setting,
)


def create_device_type_4_time_entities(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[TimeEntity]:
    entities: List[TimeEntity] = []

    for dev in devices:
        if str(dev.get("deviceType", "")) != DEVICE_TYPE_4:
            continue

        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        if dev_id is None:
            continue

        has_charge_cfg = has_charge_section(dev)

        if has_charge_setting(dev, "allowed_solar_charging_time.start") or has_charge_cfg:
            entities.append(
                DeviceType4AllowedSolarChargingTime(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    setting_key="start",
                    key="charge_allowed_solar_charging_start",
                    name="6.2 Start Time",
                )
            )

        if has_charge_setting(dev, "allowed_solar_charging_time.stop") or has_charge_cfg:
            entities.append(
                DeviceType4AllowedSolarChargingTime(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    setting_key="stop",
                    key="charge_allowed_solar_charging_stop",
                    name="6.3 Stop Time",
                )
            )

        for idx in range(3):
            if (
                has_mode_window_setting(
                    dev,
                    mode_id=MODE_TIME_WINDOW,
                    window_index=idx,
                    setting_key="start",
                )
                or has_charge_cfg
            ):
                entities.append(
                    DeviceType4WindowChargingTime(
                        coordinator=coordinator,
                        entry=entry,
                        client=client,
                        device=dev,
                        device_id=int(dev_id),
                        window_index=idx,
                        setting_key="start",
                        key=f"charge_mode_2_window_{idx+1}_start",
                        name=f"9.{idx * 2 + 3} Window {idx+1} Start Time",
                    )
                )

            if (
                has_mode_window_setting(
                    dev,
                    mode_id=MODE_TIME_WINDOW,
                    window_index=idx,
                    setting_key="stop",
                )
                or has_charge_cfg
            ):
                entities.append(
                    DeviceType4WindowChargingTime(
                        coordinator=coordinator,
                        entry=entry,
                        client=client,
                        device=dev,
                        device_id=int(dev_id),
                        window_index=idx,
                        setting_key="stop",
                        key=f"charge_mode_2_window_{idx+1}_stop",
                        name=f"9.{idx * 2 + 4} Window {idx+1} Stop Time",
                    )
                )

    return entities


class DeviceType4TimeBase(DeviceBase, TimeEntity):
    _OPTIMISTIC_WINDOW = 8.0
    _REFRESH_DELAY = 4.5

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
        raw_path: str,
        icon: str,
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
            entity_category=EntityCategory.CONFIG,
            model=MODEL_NAME,
        )
        self._client = client
        self._device_id = int(device_id)
        self._optimistic_value: Optional[time] = None
        self._optimistic_until: float = 0.0

    def _find_device(self) -> Optional[Dict[str, Any]]:
        return find_device_from_coordinator(self.coordinator, self._device_id)

    @staticmethod
    def _to_time(minutes: int) -> time:
        return time(hour=minutes // 60, minute=minutes % 60)

    @staticmethod
    def _to_minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    def _clamp_minutes(self, value: int) -> int:
        return max(MINUTES_MIN, min(MINUTES_MAX, int(value)))

    def _is_blocked_by_block_charging(self, dev: Optional[Dict[str, Any]]) -> bool:
        return isinstance(dev, dict) and is_block_charging_enabled(dev)

    def _is_blocked_by_block_solar(self, dev: Optional[Dict[str, Any]]) -> bool:
        return False

    def _read_minutes(self) -> Optional[int]:
        raise NotImplementedError

    def _is_editable(self) -> bool:
        raise NotImplementedError

    async def _write_minutes(self, minutes: int) -> None:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        dev = self._find_device()
        if not dev:
            return False
        return (
            super().available
            and not self._is_blocked_by_block_charging(dev)
            and not self._is_blocked_by_block_solar(dev)
            and self._is_editable()
        )

    @property
    def native_value(self) -> Optional[time]:
        if self._optimistic_value is not None and monotonic() < self._optimistic_until:
            return self._optimistic_value
        minutes = self._read_minutes()
        if minutes is None:
            return None
        return self._to_time(minutes)

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_value is not None:
            now = monotonic()
            current_minutes = self._read_minutes()
            if (
                current_minutes is not None
                and self._optimistic_value == self._to_time(current_minutes)
            ) or now >= self._optimistic_until:
                self._optimistic_value = None
                self._optimistic_until = 0.0
        super()._handle_coordinator_update()

    async def async_set_value(self, value: time) -> None:
        dev = self._find_device()
        if self._is_blocked_by_block_charging(dev):
            raise HomeAssistantError(
                "This option is unavailable while Block Charging is enabled."
            )
        if self._is_blocked_by_block_solar(dev):
            raise HomeAssistantError(
                "6.x options are unavailable while Block Solar Charging is enabled."
            )
        if not self._is_editable():
            raise HomeAssistantError("This time value is currently not editable.")

        minutes = self._clamp_minutes(self._to_minutes(value))
        self._optimistic_value = self._to_time(minutes)
        self._optimistic_until = monotonic() + self._OPTIMISTIC_WINDOW
        self.async_write_ha_state()

        await self._write_minutes(minutes)
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()


class DeviceType4AllowedSolarChargingTime(DeviceType4TimeBase):
    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        device_id: int,
        setting_key: str,
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            client=client,
            device=device,
            device_id=device_id,
            key=key,
            name=name,
            raw_path=f"settings.0.charge.allowed_solar_charging_time.{setting_key}",
            icon="mdi:clock-outline",
        )
        self._setting_key = setting_key

    def _read_minutes(self) -> Optional[int]:
        dev = self._find_device()
        if not dev:
            return None
        value = read_charge_setting(dev, f"allowed_solar_charging_time.{self._setting_key}")
        if isinstance(value, (int, float)):
            return self._clamp_minutes(int(value))
        return None

    def _is_blocked_by_block_solar(self, dev: Optional[Dict[str, Any]]) -> bool:
        return isinstance(dev, dict) and is_block_solar_charging_enabled(dev)

    def _is_editable(self) -> bool:
        dev = self._find_device()
        if not dev:
            return False
        enabled = read_charge_setting(dev, "allowed_solar_charging_time.enabled")
        return enabled in (1, True)

    async def _write_minutes(self, minutes: int) -> None:
        dev = self._find_device()
        if not dev:
            raise HomeAssistantError("Device not found in coordinator data.")
        if not self._is_editable():
            raise HomeAssistantError(
                "Start/stop time is available only when Allow Solar Charging Only In Time Window is enabled."
            )

        payload = copy.deepcopy(dev)
        for item in ensure_charge_settings_list(payload):
            charge = item.setdefault("charge", {})
            allowed = charge.setdefault("allowed_solar_charging_time", {})
            allowed[self._setting_key] = int(minutes)

        await self._client.async_post_device_settings(payload)


class DeviceType4WindowChargingTime(DeviceType4TimeBase):
    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        device_id: int,
        window_index: int,
        setting_key: str,
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            client=client,
            device=device,
            device_id=device_id,
            key=key,
            name=name,
            raw_path=f"settings.0.charge.mode.2.windows.{window_index}.{setting_key}",
            icon="mdi:calendar-clock",
        )
        self._window_index = int(window_index)
        self._setting_key = setting_key

    def _read_minutes(self) -> Optional[int]:
        dev = self._find_device()
        if not dev:
            return None
        value = read_mode_window_setting(
            dev,
            mode_id=MODE_TIME_WINDOW,
            window_index=self._window_index,
            setting_key=self._setting_key,
        )
        if isinstance(value, (int, float)):
            return self._clamp_minutes(int(value))
        return None

    def _is_editable(self) -> bool:
        dev = self._find_device()
        if not dev:
            return False
        return read_mode_enabled(dev, MODE_TIME_WINDOW) is True

    async def _write_minutes(self, minutes: int) -> None:
        dev = self._find_device()
        if not dev:
            raise HomeAssistantError("Device not found in coordinator data.")
        if read_mode_enabled(dev, MODE_TIME_WINDOW) is not True:
            raise HomeAssistantError(
                "Window charging times are available only when Time Window Charging Enabled is turned on."
            )

        payload = copy.deepcopy(dev)
        for item in ensure_charge_settings_list(payload):
            charge = item.setdefault("charge", {})
            mode = ensure_mode_entry(charge, MODE_TIME_WINDOW)
            window = ensure_window_entry(mode, self._window_index)
            window[self._setting_key] = int(minutes)

        await self._client.async_post_device_settings(payload)
