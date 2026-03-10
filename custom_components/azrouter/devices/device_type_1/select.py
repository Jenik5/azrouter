from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
import copy
from time import monotonic

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ...const import MODEL_DEVICE_TYPE_1
from ..sensor import DeviceBase

DEVICE_TYPE_1 = "1"
MODE_OPTIONS = ["manual", "hdo", "window", "window+hdo"]


def create_device_type_1_select_entities(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[SelectEntity]:
    entities: List[SelectEntity] = []
    for dev in devices:
        if str(dev.get("deviceType", "")) != DEVICE_TYPE_1:
            continue

        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        if dev_id is None:
            continue

        if _has_boost_mode(dev):
            entities.append(
                DeviceType1BoostModeSelect(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    key="boost_mode",
                    name="4.2 Boost Mode",
                )
            )

    return entities


def _has_boost_mode(device: Dict[str, Any]) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        boost = (item or {}).get("boost", {}) or {}
        if "mode" in boost:
            return True
    return False


class DeviceType1BoostModeSelect(DeviceBase, SelectEntity):
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
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path="settings.0.boost.mode",
            unit=None,
            devclass=None,
            icon="mdi:tune-variant",
            entity_category=EntityCategory.CONFIG,
            model=MODEL_DEVICE_TYPE_1,
        )
        self._client = client
        self._device_id = int(device_id)
        self._device_type = DEVICE_TYPE_1
        self._attr_options = MODE_OPTIONS
        self._optimistic_value: Optional[str] = None
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

    def _read_mode(self) -> Optional[int]:
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
    def current_option(self) -> Optional[str]:
        if self._optimistic_value is not None and monotonic() < self._optimistic_until:
            return self._optimistic_value

        mode = self._read_mode()
        if mode is None:
            return None
        if 0 <= mode < len(MODE_OPTIONS):
            return MODE_OPTIONS[mode]
        return MODE_OPTIONS[0]

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_value is not None:
            now = monotonic()
            current = self.current_option
            if current == self._optimistic_value or now >= self._optimistic_until:
                self._optimistic_value = None
                self._optimistic_until = 0.0
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        if option not in MODE_OPTIONS:
            raise HomeAssistantError(f"Unsupported boost mode: {option}")

        dev = self._find_device_from_coordinator()
        if not dev:
            raise HomeAssistantError("Device not found in coordinator data.")

        payload = copy.deepcopy(dev)
        settings = payload.get("settings") or []
        if not isinstance(settings, list) or not settings:
            raise HomeAssistantError("Device has no settings section.")

        mode_value = MODE_OPTIONS.index(option)
        for item in settings:
            boost = item.setdefault("boost", {})
            boost["mode"] = mode_value

        self._optimistic_value = option
        self._optimistic_until = monotonic() + self._OPTIMISTIC_WINDOW
        self.async_write_ha_state()

        await self._client.async_post_device_settings(payload)
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()
