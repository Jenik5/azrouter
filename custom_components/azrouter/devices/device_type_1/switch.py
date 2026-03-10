# custom_components/azrouter/devices/device_type_1/switch.py
# -----------------------------------------------------------
# Switch entities for device_type_1 (Smart Slave).
#
# - async_create_device_entities:
#     Creates a boost switch if power.boost is present in the device payload.
#     Creates a block_solar_heating switch if present in settings[*].power.
#
# - AzRouterDeviceType1BoostSwitch:
#     Boost switch based on DeviceBoostSwitch.
#
# - DeviceType1BlockSolarHeatingSwitch:
#     Config switch based on settings[*].power.block_solar_heating.
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List
import logging
import asyncio
from time import monotonic
import copy

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity import EntityCategory

from ...api import AzRouterClient
from ...const import MODEL_DEVICE_TYPE_1
from ..switch import DeviceBoostSwitch, DeviceSwitchBase
from ..sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)

MODEL_NAME = MODEL_DEVICE_TYPE_1
DEVICE_TYPE_1 = "1"


async def async_create_device_entities(
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    client: AzRouterClient,
    device: Dict[str, Any],
) -> List[SwitchEntity]:
    """Create switch entities for a device_type_1 device."""
    entities: List[SwitchEntity] = []

    common = device.get("common", {}) or {}
    dev_id = common.get("id")
    dev_name = common.get("name", f"device-{dev_id}")

    # ------------------------------------------------------------------
    # Boost switch (power.boost)
    # ------------------------------------------------------------------
    power = device.get("power", {}) or {}
    # Some newer API payloads may omit power.boost while still exposing boost mode.
    if "boost" in power or _has_boost_mode(device):
        _LOGGER.debug(
            "device_type_1.switch: creating Boost switch for id=%s name=%s",
            dev_id,
            dev_name,
        )
        entities.append(
            AzRouterDeviceType1BoostSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                key="power_boost",
                name="Boost",
                raw_path="power.boost",
            )
        )

    # ------------------------------------------------------------------
    # Block Solar Heating switch (settings[*].power.block_solar_heating)
    # ------------------------------------------------------------------
    has_block_solar = _has_power_setting(device, "block_solar_heating")
    if not has_block_solar:
        # Fallback for payloads where bool flags are trimmed from read response.
        has_block_solar = _has_any_power_settings(device)

    if has_block_solar and dev_id is not None:
        _LOGGER.debug(
            "device_type_1.switch: creating Block Solar Heating switch for id=%s name=%s",
            dev_id,
            dev_name,
        )
        entities.append(
            DeviceType1BlockSolarHeatingSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                device_id=dev_id,
                key="power_block_solar_heating",
                name="3.2 Block Solar Heating",
            )
        )

    # ------------------------------------------------------------------
    # Additional config switches from settings[*].power
    # ------------------------------------------------------------------
    if dev_id is not None:
        has_power_section = _has_any_power_settings(device)
        setting_switches = [
            ("ignore_cycle", "3.1 Keep Heated", "mdi:radiator"),
            (
                "block_heating_from_battery",
                "3.3 Block Heating From Battery",
                "mdi:battery-off",
            ),
        ]
        for key_name, title, icon in setting_switches:
            if _has_power_setting(device, key_name) or has_power_section:
                entities.append(
                    DeviceType1PowerSettingSwitch(
                        coordinator=coordinator,
                        entry=entry,
                        client=client,
                        device=device,
                        key=f"power_{key_name}",
                        name=title,
                        setting_key=key_name,
                        icon=icon,
                    )
                )

        if _has_power_setting(device, "offline_only") or has_power_section:
            entities.append(
                DeviceType1OfflineOnlySwitch(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=device,
                    key="power_offline_only",
                    name="4.1 Apply Only If Cloud Is Offline",
                    setting_key="offline_only",
                )
            )

        if (
            _has_power_setting(device, "allowed_solar_heating_time.enabled")
            or _has_allowed_solar_time_object(device)
        ):
            entities.append(
                DeviceType1AllowedSolarTimeEnabledSwitch(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=device,
                    key="power_allowed_solar_time_enabled",
                    name="3.4 Allow Solar Heating Only In Time Window",
                )
            )

        # Connected phases are exposed as 3 independent switches.
        # If connectedPhase is missing, infer support from per-phase power output.
        phase_count = _connected_phase_count(device)
        for idx, label in enumerate(("L1", "L2", "L3")):
            if idx < phase_count:
                entities.append(
                    DeviceType1ConnectedPhaseSwitch(
                        coordinator=coordinator,
                        entry=entry,
                        client=client,
                        device=device,
                        phase_index=idx,
                        key=f"power_connected_phase_{idx+1}",
                        name=f"1.{idx+1} Connected {label}",
                    )
                )

        # Boost windows: enabled flags for windows 1..3
        for idx in range(3):
            if (
                _has_boost_window_setting(device, idx, "enabled")
                or _has_boost_window_setting(device, idx, "start")
                or _has_boost_window_setting(device, idx, "stop")
            ):
                entities.append(
                    DeviceType1BoostWindowEnabledSwitch(
                        coordinator=coordinator,
                        entry=entry,
                        client=client,
                        device=device,
                        window_index=idx,
                        key=f"boost_window_{idx+1}_enabled",
                        name=f"4.{idx+3}.1 Boost Window {idx+1} Enabled",
                    )
                )

    _LOGGER.debug(
        "device_type_1.switch: created %d switch entities for id=%s name=%s",
        len(entities),
        dev_id,
        dev_name,
    )
    return entities


def _has_power_setting(device: Dict[str, Any], setting_path: str) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False

    parts = setting_path.split(".")
    for item in settings_list:
        cur: Any = (item or {}).get("power", {})
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur is not None:
            return True
    return False


def _connected_phase_count(device: Dict[str, Any]) -> int:
    phases = (device.get("power") or {}).get("connectedPhase")
    if isinstance(phases, list) and phases:
        return min(3, len(phases))
    output = (device.get("power") or {}).get("output")
    if isinstance(output, list) and len(output) >= 3:
        return 3
    return 0


def _has_any_power_settings(device: Dict[str, Any]) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        power = (item or {}).get("power")
        if isinstance(power, dict):
            return True
    return False


def _has_allowed_solar_time_object(device: Dict[str, Any]) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        power = (item or {}).get("power", {}) or {}
        allowed = power.get("allowed_solar_heating_time")
        if isinstance(allowed, dict):
            if any(k in allowed for k in ("enabled", "start", "stop")):
                return True
    return False


def _has_boost_mode(device: Dict[str, Any]) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        boost = (item or {}).get("boost", {}) or {}
        if "mode" in boost:
            return True
    return False


def _has_boost_window_setting(device: Dict[str, Any], index: int, key: str) -> bool:
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


class AzRouterDeviceType1BoostSwitch(DeviceBoostSwitch):
    """Boost switch for device_type_1."""

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


class DeviceType1BlockSolarHeatingSwitch(DeviceBase, SwitchEntity):
    """Switch for settings[*].power.block_solar_heating on device_type_1."""

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
    ) -> None:
        # raw_path je jen informativní – čteme ručně ze settings
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path="settings.0.power.block_solar_heating",
            unit=None,
            devclass=None,
            icon="mdi:weather-sunny-off",
            entity_category=EntityCategory.CONFIG,
            model=MODEL_NAME,
        )

        self._client = client
        self._device_id = int(device_id)
        self._optimistic_state: bool | None = None
        self._optimistic_until: float = 0.0

    # ------------------------------------------------------------------
    # Interní helper: načtení aktuálního stavu z coordinator.data
    # ------------------------------------------------------------------
    def _get_current_flag(self) -> bool | None:
        data = self.coordinator.data or {}
        devices = data.get("devices", [])

        for dev in devices:
            try:
                dev_type = str(dev.get("deviceType"))
                common = dev.get("common", {}) or {}
                cid = int(common.get("id", -1))
            except Exception:
                continue

            if dev_type != DEVICE_TYPE_1 or cid != self._device_id:
                continue

            settings_list = dev.get("settings") or []
            if not settings_list:
                return None

            # čteme první profil (settings[0]) – ale zápis půjde do obou
            power = settings_list[0].get("power", {}) or {}
            val = power.get("block_solar_heating")
            if val is None:
                return None

            try:
                return bool(int(val))
            except Exception:
                return bool(val)

        return None

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None and monotonic() < self._optimistic_until:
            return self._optimistic_state
        val = self._get_current_flag()
        return bool(val) if val is not None else False

    def _handle_coordinator_update(self) -> None:
        current = self._get_current_flag()
        if self._optimistic_state is not None:
            now = monotonic()
            if current is not None and bool(current) == self._optimistic_state:
                self._optimistic_state = None
                self._optimistic_until = 0.0
            elif now >= self._optimistic_until:
                self._optimistic_state = None
                self._optimistic_until = 0.0
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs) -> None:
        self._optimistic_state = True
        self._optimistic_until = monotonic() + self._OPTIMISTIC_WINDOW
        self.async_write_ha_state()
        await self._client.async_set_device_type_1_power_setting(
            self._device_id,
            path="block_solar_heating",
            value=1,
        )
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        self._optimistic_state = False
        self._optimistic_until = monotonic() + self._OPTIMISTIC_WINDOW
        self.async_write_ha_state()
        await self._client.async_set_device_type_1_power_setting(
            self._device_id,
            path="block_solar_heating",
            value=0,
        )
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()


class DeviceType1PowerSettingSwitch(DeviceSwitchBase):
    """Boolean switch for settings[*].power.<setting_key> on device_type_1."""

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        key: str,
        name: str,
        setting_key: str,
        icon: str | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            device=device,
            key=key,
            name=name,
            raw_path=f"settings.0.power.{setting_key}",
            model=MODEL_NAME,
            icon=icon,
        )
        self._client = client
        self._setting_key = setting_key
        self._attr_entity_category = EntityCategory.CONFIG

    def _find_device_from_coordinator(self) -> Dict[str, Any] | None:
        data = self.coordinator.data or {}
        devices = data.get("devices") or []
        for dev in devices:
            try:
                if (
                    str(dev.get("deviceType")) == DEVICE_TYPE_1
                    and int(dev.get("common", {}).get("id", -1)) == int(self._device_id)
                ):
                    return dev
            except Exception:
                continue
        return None

    async def _send_value(self, value: bool) -> None:
        dev = self._find_device_from_coordinator()
        if not dev:
            raise HomeAssistantError("Device is not available in coordinator data.")

        payload = copy.deepcopy(dev)
        settings_list = payload.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            raise HomeAssistantError("Device has no settings section.")

        int_value = 1 if value else 0
        for item in settings_list:
            power = item.setdefault("power", {})
            power[self._setting_key] = int_value

        await self._client.async_post_device_settings(payload)

    def _read_boost_mode(self) -> int | None:
        dev = self._find_device_from_coordinator()
        if not dev:
            return None
        settings_list = dev.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            return None
        mode = ((settings_list[0].get("boost") or {}).get("mode"))
        if isinstance(mode, (int, float)):
            return int(mode)
        return None


class DeviceType1AllowedSolarTimeEnabledSwitch(DeviceType1PowerSettingSwitch):
    """Switch for settings[*].power.allowed_solar_heating_time.enabled."""

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
            key=key,
            name=name,
            setting_key="__nested__",
            icon="mdi:clock-check-outline",
        )
        self._raw_path = "settings.0.power.allowed_solar_heating_time.enabled"

    async def _send_value(self, value: bool) -> None:
        dev = self._find_device_from_coordinator()
        if not dev:
            raise HomeAssistantError("Device is not available in coordinator data.")

        payload = copy.deepcopy(dev)
        settings_list = payload.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            raise HomeAssistantError("Device has no settings section.")

        int_value = 1 if value else 0
        for item in settings_list:
            power = item.setdefault("power", {})
            allowed = power.setdefault("allowed_solar_heating_time", {})
            allowed["enabled"] = int_value

        await self._client.async_post_device_settings(payload)


class DeviceType1OfflineOnlySwitch(DeviceType1PowerSettingSwitch):
    """Switch for settings[*].power.offline_only with mode-aware availability."""

    @property
    def available(self) -> bool:
        mode = self._read_boost_mode()
        return super().available and mode is not None and mode != 0

    async def _send_value(self, value: bool) -> None:
        mode = self._read_boost_mode()
        if mode is None:
            raise HomeAssistantError("Boost mode is not available.")
        if mode == 0:
            raise HomeAssistantError("Apply Only If Cloud Is Offline is disabled in manual mode.")
        await super()._send_value(value)


class DeviceType1BoostWindowEnabledSwitch(DeviceSwitchBase):
    """Switch for settings[*].boost.windows[index].enabled."""

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        window_index: int,
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            device=device,
            key=key,
            name=name,
            raw_path=f"settings.0.boost.windows.{window_index}.enabled",
            model=MODEL_NAME,
            icon="mdi:calendar-clock",
        )
        self._client = client
        self._window_index = int(window_index)
        self._attr_entity_category = EntityCategory.CONFIG

    def _find_device_from_coordinator(self) -> Dict[str, Any] | None:
        data = self.coordinator.data or {}
        devices = data.get("devices") or []
        for dev in devices:
            try:
                if (
                    str(dev.get("deviceType")) == DEVICE_TYPE_1
                    and int(dev.get("common", {}).get("id", -1)) == int(self._device_id)
                ):
                    return dev
            except Exception:
                continue
        return None

    def _read_boost_mode(self) -> int | None:
        dev = self._find_device_from_coordinator()
        if not dev:
            return None
        settings_list = dev.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            return None
        mode = ((settings_list[0].get("boost") or {}).get("mode"))
        if isinstance(mode, (int, float)):
            return int(mode)
        return None

    @property
    def available(self) -> bool:
        mode = self._read_boost_mode()
        return super().available and mode in (2, 3)

    async def _send_value(self, value: bool) -> None:
        dev = self._find_device_from_coordinator()
        if not dev:
            raise HomeAssistantError("Device is not available in coordinator data.")

        mode = self._read_boost_mode()
        if mode not in (2, 3):
            raise HomeAssistantError("Boost windows are available only in window/window+hdo mode.")

        payload = copy.deepcopy(dev)
        settings_list = payload.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            raise HomeAssistantError("Device has no settings section.")

        int_value = 1 if value else 0
        for item in settings_list:
            boost = item.setdefault("boost", {})
            windows = boost.setdefault("windows", [])
            while len(windows) <= self._window_index:
                windows.append({"enabled": 0, "start": 0, "stop": 0})
            window = windows[self._window_index]
            if not isinstance(window, dict):
                window = {}
                windows[self._window_index] = window
            window["enabled"] = int_value

        await self._client.async_post_device_settings(payload)


class DeviceType1ConnectedPhaseSwitch(DeviceSwitchBase):
    """Switch for power.connectedPhase[index] on device_type_1."""

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        phase_index: int,
        key: str,
        name: str,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            device=device,
            key=key,
            name=name,
            raw_path=f"power.connectedPhase.{phase_index}",
            model=MODEL_NAME,
            icon="mdi:sine-wave",
        )
        self._client = client
        self._phase_index = int(phase_index)
        self._attr_entity_category = EntityCategory.CONFIG

    def _find_device_from_coordinator(self) -> Dict[str, Any] | None:
        data = self.coordinator.data or {}
        devices = data.get("devices") or []
        for dev in devices:
            try:
                if (
                    str(dev.get("deviceType")) == DEVICE_TYPE_1
                    and int(dev.get("common", {}).get("id", -1)) == int(self._device_id)
                ):
                    return dev
            except Exception:
                continue
        return None

    async def _send_value(self, value: bool) -> None:
        dev = self._find_device_from_coordinator()
        if not dev:
            raise HomeAssistantError("Device is not available in coordinator data.")

        await self._client.async_set_device_type_1_connected_phase(
            self._device_id, self._phase_index, value
        )

# End Of File
