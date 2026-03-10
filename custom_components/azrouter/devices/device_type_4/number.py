from __future__ import annotations

from typing import Any, Dict, List, Optional
import copy
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..number import DeviceNumberBase
from .helpers import (
    CHARGING_POWER_STEP,
    DEFAULT_MAX_POWER,
    DEVICE_TYPE_4,
    MAX_TRIGGER_DURATION,
    MAX_TRIGGER_POWER,
    MIN_CHARGING_POWER,
    MIN_TRIGGER_DURATION,
    MIN_TRIGGER_POWER,
    MODE_HDO,
    MODE_MANUAL,
    MODE_PRIORITIZE_WHEN_CONNECTED,
    MODE_TIME_WINDOW,
    MODEL_NAME,
    TRIGGER_DURATION_STEP,
    TRIGGER_POWER_STEP,
    ensure_charge_settings_list,
    ensure_mode_entry,
    find_device_from_coordinator,
    get_breaker_limit,
    has_charge_section,
    has_mode_setting,
    is_block_charging_enabled,
    is_block_solar_charging_enabled,
    read_mode_setting,
)

_LOGGER = logging.getLogger(__name__)


def create_device_type_4_numbers(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[NumberEntity]:
    entities: List[NumberEntity] = []

    for dev in devices:
        if str(dev.get("deviceType", "")) != DEVICE_TYPE_4:
            continue

        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        if dev_id is None:
            continue

        has_charge_cfg = has_charge_section(dev)

        if has_mode_setting(dev, MODE_PRIORITIZE_WHEN_CONNECTED, "triggerOnPower") or has_charge_cfg:
            entities.append(
                DeviceType4ModeNumber(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    mode_id=MODE_PRIORITIZE_WHEN_CONNECTED,
                    setting_key="triggerOnPower",
                    key="charge_mode_0_trigger_on_power",
                    name="6.4 Trigger On Power",
                    icon="mdi:flash-outline",
                    unit=UnitOfPower.WATT,
                    native_min=MIN_TRIGGER_POWER,
                    native_max=MAX_TRIGGER_POWER,
                    native_step=TRIGGER_POWER_STEP,
                )
            )

        if has_mode_setting(dev, MODE_PRIORITIZE_WHEN_CONNECTED, "triggerOnDuration") or has_charge_cfg:
            entities.append(
                DeviceType4ModeNumber(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    mode_id=MODE_PRIORITIZE_WHEN_CONNECTED,
                    setting_key="triggerOnDuration",
                    key="charge_mode_0_trigger_on_duration",
                    name="6.5 Trigger On Duration",
                    icon="mdi:timer-outline",
                    unit="s",
                    native_min=MIN_TRIGGER_DURATION,
                    native_max=MAX_TRIGGER_DURATION,
                    native_step=TRIGGER_DURATION_STEP,
                )
            )

        if has_mode_setting(dev, MODE_PRIORITIZE_WHEN_CONNECTED, "triggerOffPower") or has_charge_cfg:
            entities.append(
                DeviceType4ModeNumber(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    mode_id=MODE_PRIORITIZE_WHEN_CONNECTED,
                    setting_key="triggerOffPower",
                    key="charge_mode_0_trigger_off_power",
                    name="6.6 Trigger Off Power",
                    icon="mdi:flash-off-outline",
                    unit=UnitOfPower.WATT,
                    native_min=MIN_TRIGGER_POWER,
                    native_max=MAX_TRIGGER_POWER,
                    native_step=TRIGGER_POWER_STEP,
                )
            )

        if has_mode_setting(dev, MODE_PRIORITIZE_WHEN_CONNECTED, "triggerOffDuration") or has_charge_cfg:
            entities.append(
                DeviceType4ModeNumber(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    mode_id=MODE_PRIORITIZE_WHEN_CONNECTED,
                    setting_key="triggerOffDuration",
                    key="charge_mode_0_trigger_off_duration",
                    name="6.7 Trigger Off Duration",
                    icon="mdi:timer-off-outline",
                    unit="s",
                    native_min=MIN_TRIGGER_DURATION,
                    native_max=MAX_TRIGGER_DURATION,
                    native_step=TRIGGER_DURATION_STEP,
                )
            )

        if has_mode_setting(dev, MODE_MANUAL, "power") or has_charge_cfg:
            entities.append(
                DeviceType4ModeNumber(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    mode_id=MODE_MANUAL,
                    setting_key="power",
                    key="charge_manual_power",
                    name="7.1 Manual Charging Power",
                    icon="mdi:flash",
                    unit=UnitOfPower.WATT,
                    native_min=MIN_CHARGING_POWER,
                    native_max=DEFAULT_MAX_POWER,
                    native_step=CHARGING_POWER_STEP,
                    dynamic_breaker_limit=True,
                    force_mode_enabled=True,
                )
            )

        if has_mode_setting(dev, MODE_TIME_WINDOW, "power") or has_charge_cfg:
            entities.append(
                DeviceType4ModeNumber(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    mode_id=MODE_TIME_WINDOW,
                    setting_key="power",
                    key="charge_mode_2_power",
                    name="9.2 Power",
                    icon="mdi:calendar-clock",
                    unit=UnitOfPower.WATT,
                    native_min=MIN_CHARGING_POWER,
                    native_max=DEFAULT_MAX_POWER,
                    native_step=CHARGING_POWER_STEP,
                    dynamic_breaker_limit=True,
                )
            )

        if has_mode_setting(dev, MODE_HDO, "power") or has_charge_cfg:
            entities.append(
                DeviceType4ModeNumber(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    mode_id=MODE_HDO,
                    setting_key="power",
                    key="charge_mode_3_power",
                    name="10.2 HDO Charging Power",
                    icon="mdi:transmission-tower",
                    unit=UnitOfPower.WATT,
                    native_min=MIN_CHARGING_POWER,
                    native_max=DEFAULT_MAX_POWER,
                    native_step=CHARGING_POWER_STEP,
                    dynamic_breaker_limit=True,
                )
            )

    return entities


class DeviceType4ModeNumber(DeviceNumberBase):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        device_id: int,
        mode_id: int,
        setting_key: str,
        key: str,
        name: str,
        icon: str,
        unit: str | None,
        native_min: int,
        native_max: int,
        native_step: int,
        dynamic_breaker_limit: bool = False,
        force_mode_enabled: bool = False,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path="",
            unit=unit,
            devclass=None,
            icon=icon,
            entity_category=EntityCategory.CONFIG,
            model=MODEL_NAME,
        )
        self._client = client
        self._device_id = int(device_id)
        self._mode_id = int(mode_id)
        self._setting_key = setting_key
        self._dynamic_breaker_limit = dynamic_breaker_limit
        self._force_mode_enabled = force_mode_enabled
        self._static_min = int(native_min)
        self._static_max = int(native_max)
        self._static_step = int(native_step)
        self._attr_native_min_value = float(native_min)
        self._attr_native_max_value = float(native_max)
        self._attr_native_step = float(native_step)

    def _find_device(self) -> Optional[Dict[str, Any]]:
        return find_device_from_coordinator(self.coordinator, self._device_id)

    def _is_blocked_by_block_charging(self, dev: Optional[Dict[str, Any]]) -> bool:
        return isinstance(dev, dict) and is_block_charging_enabled(dev)

    def _is_blocked_by_block_solar(self, dev: Optional[Dict[str, Any]]) -> bool:
        return (
            isinstance(dev, dict)
            and self._mode_id == MODE_PRIORITIZE_WHEN_CONNECTED
            and is_block_solar_charging_enabled(dev)
        )

    def _current_max_limit(self) -> int:
        if not self._dynamic_breaker_limit:
            return self._static_max
        return max(self._static_min, get_breaker_limit(self._find_device()))

    def _clamp(self, value: float | int) -> int:
        ivalue = int(round(float(value)))
        max_limit = self._current_max_limit()
        if ivalue < self._static_min:
            ivalue = self._static_min
        if ivalue > max_limit:
            ivalue = max_limit

        step = max(1, self._static_step)
        remainder = (ivalue - self._static_min) % step
        if remainder != 0:
            ivalue -= remainder
        return ivalue

    def _update_from_coordinator(self) -> None:
        dev = self._find_device()
        if not dev:
            return

        self._attr_native_max_value = float(self._current_max_limit())
        value = read_mode_setting(dev, self._mode_id, self._setting_key)
        if isinstance(value, (int, float)):
            self._value = float(self._clamp(value))

    @property
    def available(self) -> bool:
        dev = self._find_device()
        if not dev:
            return False
        return (
            super().available
            and not self._is_blocked_by_block_charging(dev)
            and not self._is_blocked_by_block_solar(dev)
        )

    async def _async_send_value(self, value: float | int) -> None:
        dev = self._find_device()
        if not dev:
            return
        if self._is_blocked_by_block_charging(dev):
            raise HomeAssistantError(
                "This option is unavailable while Block Charging is enabled."
            )
        if self._is_blocked_by_block_solar(dev):
            raise HomeAssistantError(
                "6.x options are unavailable while Block Solar Charging is enabled."
            )

        payload = copy.deepcopy(dev)
        int_value = self._clamp(value)
        for item in ensure_charge_settings_list(payload):
            charge = item.setdefault("charge", {})
            mode = ensure_mode_entry(charge, self._mode_id)
            if self._force_mode_enabled:
                mode["enabled"] = 1
            mode[self._setting_key] = int_value

        _LOGGER.debug(
            "device_type_4.number: device=%s mode=%s %s=%s",
            self._device_id,
            self._mode_id,
            self._setting_key,
            int_value,
        )
        await self._client.async_post_device_settings(payload)
