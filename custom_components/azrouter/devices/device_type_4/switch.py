from __future__ import annotations

from typing import Any, Dict, List
import copy
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.switch import SwitchEntity

from ...api import AzRouterClient
from ..switch import DeviceBoostSwitch, DeviceSwitchBase
from .helpers import (
    DEVICE_TYPE_4,
    MODE_HDO,
    MODE_PRIORITIZE_WHEN_CONNECTED,
    MODE_TIME_WINDOW,
    MODEL_NAME,
    ensure_charge_settings_list,
    ensure_mode_entry,
    find_device_from_coordinator,
    has_charge_section,
    has_charge_setting,
    has_mode_setting,
    is_block_charging_enabled,
    is_block_solar_charging_enabled,
    read_mode_enabled,
    read_mode_setting,
    set_nested_dict_value,
)

_LOGGER = logging.getLogger(__name__)


async def async_create_device_entities(
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    client: AzRouterClient,
    device: Dict[str, Any],
) -> List[SwitchEntity]:
    """Create switch entities for a device_type_4 (charger) device."""
    entities: List[SwitchEntity] = []

    if str(device.get("deviceType", "")) != DEVICE_TYPE_4:
        return entities

    common = device.get("common", {}) or {}
    dev_id = common.get("id")
    if dev_id is None:
        return entities

    charge = device.get("charge", {}) or {}
    has_charge_cfg = has_charge_section(device)

    if "boost" in charge:
        entities.append(
            AzRouterDeviceType4BoostSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                key="charge_boost",
                name="Boost",
                raw_path="charge.boost",
            )
        )

    if has_charge_setting(device, "block_charging") or has_charge_cfg:
        entities.append(
            DeviceType4ChargeSettingSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                setting_path="block_charging",
                key="charge_block_charging",
                name="1. Block Charging",
                icon="mdi:power-plug-off",
            )
        )

    if has_mode_setting(device, MODE_PRIORITIZE_WHEN_CONNECTED, "enabled") or has_charge_cfg:
        entities.append(
            DeviceType4ModeEnabledSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                mode_id=MODE_PRIORITIZE_WHEN_CONNECTED,
                key="charge_prioritize_when_connected",
                name="2. Prioritize When Connected",
                icon="mdi:connection",
            )
        )

    if has_charge_setting(device, "block_solar_charging") or has_charge_cfg:
        entities.append(
            DeviceType4ChargeSettingSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                setting_path="block_solar_charging",
                key="charge_block_solar_charging",
                name="3. Block Solar Charging",
                icon="mdi:weather-sunny-off",
            )
        )

    if has_charge_setting(device, "block_charging_from_battery") or has_charge_cfg:
        entities.append(
            DeviceType4ChargeSettingSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                setting_path="block_charging_from_battery",
                key="charge_block_charging_from_battery",
                name="4. Block Charging From Battery",
                icon="mdi:battery-off-outline",
            )
        )

    if (
        has_charge_setting(device, "allowed_solar_charging_time.enabled")
        or has_charge_setting(device, "allowed_solar_charging_time")
        or has_charge_cfg
    ):
        entities.append(
            DeviceType4AllowedSolarChargingTimeEnabledSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                key="charge_allowed_solar_time_enabled",
                name="6.1 Allow Solar Charging Only In Time Window",
            )
        )

    if has_charge_setting(device, "offline_only") or has_charge_cfg:
        entities.append(
            DeviceType4OfflineOnlySwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                key="charge_offline_only",
                name="8. Apply Only If Cloud Is Offline",
            )
        )

    if has_mode_setting(device, MODE_TIME_WINDOW, "enabled") or has_charge_cfg:
        entities.append(
            DeviceType4ModeEnabledSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                mode_id=MODE_TIME_WINDOW,
                key="charge_mode_2_enabled",
                name="9.1 Time Window Charging Enabled",
                icon="mdi:calendar-clock",
            )
        )

    if has_mode_setting(device, MODE_HDO, "enabled") or has_charge_cfg:
        entities.append(
            DeviceType4ModeEnabledSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                mode_id=MODE_HDO,
                key="charge_mode_3_enabled",
                name="10.1 HDO Charging Enabled",
                icon="mdi:transmission-tower",
            )
        )

    return entities


class AzRouterDeviceType4BoostSwitch(DeviceBoostSwitch):
    """Boost switch for device_type_4 (charger)."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        key: str,
        name: str,
        raw_path: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            client=client,
            device=device,
            key=key,
            name=name,
            raw_path=raw_path,
            model=MODEL_NAME,
        )


class DeviceType4ChargeSettingSwitch(DeviceSwitchBase):
    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        setting_path: str,
        key: str,
        name: str,
        icon: str | None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            device=device,
            key=key,
            name=name,
            raw_path=f"settings.0.charge.{setting_path}",
            model=MODEL_NAME,
            icon=icon,
        )
        self._client = client
        self._setting_path = setting_path
        self._attr_entity_category = EntityCategory.CONFIG

    def _find_device(self) -> Dict[str, Any] | None:
        return find_device_from_coordinator(self.coordinator, self._device_id)

    def _is_blocked_by_block_charging(self, dev: Dict[str, Any]) -> bool:
        return self._setting_path != "block_charging" and is_block_charging_enabled(dev)

    def _is_blocked_by_block_solar(self, dev: Dict[str, Any]) -> bool:
        return (
            self._setting_path.startswith("allowed_solar_charging_time.")
            and is_block_solar_charging_enabled(dev)
        )

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

    async def _send_value(self, value: bool) -> None:
        dev = self._find_device()
        if not dev:
            raise HomeAssistantError("Device is not available in coordinator data.")
        if self._is_blocked_by_block_charging(dev):
            raise HomeAssistantError(
                "This option is unavailable while Block Charging is enabled."
            )
        if self._is_blocked_by_block_solar(dev):
            raise HomeAssistantError(
                "6.x options are unavailable while Block Solar Charging is enabled."
            )

        payload = copy.deepcopy(dev)
        int_value = 1 if value else 0
        for item in ensure_charge_settings_list(payload):
            charge = item.setdefault("charge", {})
            set_nested_dict_value(charge, self._setting_path, int_value)

        await self._client.async_post_device_settings(payload)


class DeviceType4AllowedSolarChargingTimeEnabledSwitch(DeviceType4ChargeSettingSwitch):
    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            client=client,
            device=device,
            setting_path="allowed_solar_charging_time.enabled",
            key=key,
            name=name,
            icon="mdi:clock-check-outline",
        )


class DeviceType4OfflineOnlySwitch(DeviceType4ChargeSettingSwitch):
    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            client=client,
            device=device,
            setting_path="offline_only",
            key=key,
            name=name,
            icon="mdi:cloud-off-outline",
        )

    @property
    def available(self) -> bool:
        dev = self._find_device()
        if not dev:
            return False
        mode2_enabled = read_mode_enabled(dev, MODE_TIME_WINDOW)
        mode3_enabled = read_mode_enabled(dev, MODE_HDO)
        return super().available and (mode2_enabled is True or mode3_enabled is True)

    async def _send_value(self, value: bool) -> None:
        dev = self._find_device()
        if not dev:
            raise HomeAssistantError("Device is not available in coordinator data.")

        mode2_enabled = read_mode_enabled(dev, MODE_TIME_WINDOW)
        mode3_enabled = read_mode_enabled(dev, MODE_HDO)
        if mode2_enabled is not True and mode3_enabled is not True:
            raise HomeAssistantError(
                "Apply Only If Cloud Is Offline is available only when Time Window or HDO charging is enabled."
            )

        await super()._send_value(value)


class DeviceType4ModeEnabledSwitch(DeviceSwitchBase):
    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        mode_id: int,
        key: str,
        name: str,
        icon: str | None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            device=device,
            key=key,
            name=name,
            raw_path=f"settings.0.charge.mode.{mode_id}.enabled",
            model=MODEL_NAME,
            icon=icon,
        )
        self._client = client
        self._mode_id = int(mode_id)
        self._attr_entity_category = EntityCategory.CONFIG

    def _find_device(self) -> Dict[str, Any] | None:
        return find_device_from_coordinator(self.coordinator, self._device_id)

    def _read_raw(self) -> Any:
        dev = self._find_device()
        if not dev:
            return None
        return read_mode_setting(dev, self._mode_id, "enabled")

    @property
    def available(self) -> bool:
        dev = self._find_device()
        if not dev:
            return False
        return super().available and not is_block_charging_enabled(dev)

    async def _send_value(self, value: bool) -> None:
        dev = self._find_device()
        if not dev:
            raise HomeAssistantError("Device is not available in coordinator data.")
        if is_block_charging_enabled(dev):
            raise HomeAssistantError(
                "This option is unavailable while Block Charging is enabled."
            )

        payload = copy.deepcopy(dev)
        int_value = 1 if value else 0
        for item in ensure_charge_settings_list(payload):
            charge = item.setdefault("charge", {})
            mode = ensure_mode_entry(charge, self._mode_id)
            mode["enabled"] = int_value

        await self._client.async_post_device_settings(payload)
