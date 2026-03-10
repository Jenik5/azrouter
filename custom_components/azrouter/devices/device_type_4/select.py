from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
from time import monotonic

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..sensor import DeviceBase
from .helpers import (
    DEVICE_TYPE_4,
    MODEL_NAME,
    PHASE_OPTIONS,
    find_device_from_coordinator,
    is_block_charging_enabled,
)


def create_device_type_4_select_entities(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[SelectEntity]:
    entities: List[SelectEntity] = []

    for dev in devices:
        if str(dev.get("deviceType", "")) != DEVICE_TYPE_4:
            continue

        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        if dev_id is None:
            continue

        charge = dev.get("charge", {}) or {}
        if "triggerPhase" in charge or charge:
            entities.append(
                DeviceType4TriggerPhaseSelect(
                    coordinator=coordinator,
                    entry=entry,
                    client=client,
                    device=dev,
                    device_id=int(dev_id),
                    key="charge_trigger_phase",
                    name="5. Triggering Phase",
                )
            )

    return entities


class DeviceType4TriggerPhaseSelect(DeviceBase, SelectEntity):
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
            raw_path="charge.triggerPhase",
            unit=None,
            devclass=None,
            icon="mdi:sine-wave",
            entity_category=EntityCategory.CONFIG,
            model=MODEL_NAME,
        )
        self._client = client
        self._device_id = int(device_id)
        self._attr_options = PHASE_OPTIONS
        self._optimistic_value: Optional[str] = None
        self._optimistic_until: float = 0.0

    def _find_device(self) -> Optional[Dict[str, Any]]:
        return find_device_from_coordinator(self.coordinator, self._device_id)

    def _read_phase_option(self) -> Optional[str]:
        dev = self._find_device()
        if not dev:
            return None

        raw_value = (dev.get("charge", {}) or {}).get("triggerPhase")
        if isinstance(raw_value, str):
            normalized = raw_value.strip().upper()
            if normalized in PHASE_OPTIONS:
                return normalized
            try:
                raw_value = int(normalized)
            except Exception:
                return None

        if isinstance(raw_value, (int, float)):
            idx = int(raw_value)
            if 0 <= idx < len(PHASE_OPTIONS):
                return PHASE_OPTIONS[idx]
        return None

    @property
    def available(self) -> bool:
        dev = self._find_device()
        if not dev:
            return False
        return super().available and not is_block_charging_enabled(dev)

    @property
    def current_option(self) -> Optional[str]:
        if self._optimistic_value is not None and monotonic() < self._optimistic_until:
            return self._optimistic_value
        return self._read_phase_option()

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_value is not None:
            now = monotonic()
            if self._read_phase_option() == self._optimistic_value or now >= self._optimistic_until:
                self._optimistic_value = None
                self._optimistic_until = 0.0
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        if option not in PHASE_OPTIONS:
            raise HomeAssistantError(f"Unsupported trigger phase: {option}")
        dev = self._find_device()
        if dev and is_block_charging_enabled(dev):
            raise HomeAssistantError(
                "This option is unavailable while Block Charging is enabled."
            )

        self._optimistic_value = option
        self._optimistic_until = monotonic() + self._OPTIMISTIC_WINDOW
        self.async_write_ha_state()

        await self._client.async_set_device_type_4_trigger_phase(
            self._device_id,
            PHASE_OPTIONS.index(option),
        )
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()
