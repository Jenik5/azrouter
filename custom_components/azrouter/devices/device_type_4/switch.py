# custom_components/azrouter/devices/device_type_4/switch.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)
LOG_PREFIX = "AZR/devices/type_4/switch"


async def async_create_device_entities(
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    client: AzRouterClient,
    device: Dict[str, Any],
) -> List[SwitchEntity]:
    """Switche pro deviceType=4 (charger). Zatím jen Boost."""

    entities: List[SwitchEntity] = []

    common = device.get("common", {}) or {}
    dev_id = common.get("id")
    dev_name = common.get("name", f"device-{dev_id}")

    charge = device.get("charge", {}) or {}
    if "boost" in charge:
        _LOGGER.debug(
            "%s: creating Boost switch for deviceType=4 id=%s name=%s",
            LOG_PREFIX,
            dev_id,
            dev_name,
        )
        entities.append(
            AzRouterDeviceType4BoostSwitch(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=device,
                key="charge_boost",
                name=f"{dev_name} Boost",
                raw_path="charge.boost",
            )
        )

    return entities


class AzRouterDeviceType4BoostSwitch(DeviceBase, SwitchEntity):
    """Boost switch pro deviceType=4 (charger)."""

    _REFRESH_DELAY = 0.8

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
            key=key,
            name=name,
            device=device,
            raw_path=raw_path,
            unit=None,
            devclass=None,
            icon="mdi:flash-outline",
            entity_category=None,
            model="AZ Charger Cube",  # kdyžtak uprav podle reality
        )

        self._client = client

    @property
    def is_on(self) -> Optional[bool]:
        """Stav boostu z charge.boost přes DeviceBase._read_raw()."""
        val = self._read_raw()
        if val is None:
            return None

        try:
            if isinstance(val, bool):
                return bool(val)
            ival = int(val)
            return ival != 0
        except Exception:
            s = str(val).lower()
            if s in ("on", "true", "yes", "1"):
                return True
            if s in ("off", "false", "no", "0"):
                return False
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        _LOGGER.debug("%s: turning ON boost (id=%s)", LOG_PREFIX, self._device_id)

        if self._client is None or self._device_id is None:
            _LOGGER.error(
                "%s: cannot turn ON boost, missing client or device_id", LOG_PREFIX
            )
            return

        try:
            await self._client.async_set_device_boost(self._device_id, True)
        except Exception as exc:
            _LOGGER.error(
                "%s: async_set_device_boost(True) failed for id=%s: %s",
                LOG_PREFIX,
                self._device_id,
                exc,
            )
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        _LOGGER.debug("%s: turning OFF boost (id=%s)", LOG_PREFIX, self._device_id)

        if self._client is None or self._device_id is None:
            _LOGGER.error(
                "%s: cannot turn OFF boost, missing client or device_id", LOG_PREFIX
            )
            return

        try:
            await self._client.async_set_device_boost(self._device_id, False)
        except Exception as exc:
            _LOGGER.error(
                "%s: async_set_device_boost(False) failed for id=%s: %s",
                LOG_PREFIX,
                self._device_id,
                exc,
            )
        await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()
