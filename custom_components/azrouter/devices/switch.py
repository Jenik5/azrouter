# custom_components/azrouter/devices/switch.py
# -----------------------------------------------------------
# Shared switch base classes for device-level and master switches.
#
# - DeviceSwitchBase:
#     Base for all device-level switches (per-device entities).
#
# - DeviceBoostSwitch:
#     Specialization for "boost" switches that write using
#     AzRouterClient.async_set_device_boost(device_id, value).
#
# - MasterSwitchBase:
#     Base for master-level switches (on the main AZ Router unit).
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, Optional
import logging
import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..api import AzRouterClient
from .sensor import DeviceBase, MasterBase

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Device-level switch base
# ---------------------------------------------------------------------------

class DeviceSwitchBase(DeviceBase, SwitchEntity):
    """Base class for all device-level switches."""

    _REFRESH_DELAY = 0.8  # seconds, used after write before requesting refresh

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        device: Dict[str, Any],
        key: str,
        name: str,
        raw_path: str,
        *,
        model: str,
        icon: str | None = None,
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
            entity_category=None,
            model=model,
        )

    def _parse_bool(self, value: Any) -> Optional[bool]:
        """Try to convert raw value to bool, return None if unknown."""
        if value is None:
            return None

        try:
            if isinstance(value, bool):
                return bool(value)
            ival = int(value)
            return ival != 0
        except Exception:
            s = str(value).lower()
            if s in ("on", "true", "yes", "1"):
                return True
            if s in ("off", "false", "no", "0"):
                return False
        return None

    @property
    def is_on(self) -> Optional[bool]:
        """Return the current switch state as boolean, if available."""
        raw = self._read_raw()
        return self._parse_bool(raw)

    async def _send_value(self, value: bool) -> None:  # pragma: no cover - abstract
        """Send new state to the device. Must be implemented by subclasses."""
        raise NotImplementedError()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on and request a refresh afterwards."""
        try:
            await self._send_value(True)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "DeviceSwitchBase: failed to send ON value for %s: %s",
                getattr(self, "_attr_unique_id", "?"),
                exc,
            )

        if self._REFRESH_DELAY > 0:
            await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off and request a refresh afterwards."""
        try:
            await self._send_value(False)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "DeviceSwitchBase: failed to send OFF value for %s: %s",
                getattr(self, "_attr_unique_id", "?"),
                exc,
            )

        if self._REFRESH_DELAY > 0:
            await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()


class DeviceBoostSwitch(DeviceSwitchBase):
    """Boost switch implementation for device-level devices."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
        device: Dict[str, Any],
        key: str,
        name: str,
        raw_path: str,
        *,
        model: str,
        icon: str = "mdi:flash-outline",
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            device=device,
            key=key,
            name=name,
            raw_path=raw_path,
            model=model,
            icon=icon,
        )
        self._client = client

    async def _send_value(self, value: bool) -> None:
        if self._client is None or self._device_id is None:
            _LOGGER.error(
                "DeviceBoostSwitch: cannot send value %s, missing client or device_id",
                value,
            )
            return

        await self._client.async_set_device_boost(self._device_id, value)


# ---------------------------------------------------------------------------
# Master-level switch base
# ---------------------------------------------------------------------------

class MasterSwitchBase(MasterBase, SwitchEntity):
    """Base class for master-level switches (on the main AZ Router unit)."""

    _REFRESH_DELAY = 0.0  # usually fast to update via /status

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        raw_path: str,
        *,
        icon: str | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            raw_path=raw_path,
            unit=None,
            devclass=None,
            icon=icon,
            entity_category=None,
        )
        # Force normal toggle UI instead of two separate buttons
        self._attr_assumed_state = False

    def _parse_bool(self, value: Any) -> Optional[bool]:
        """Try to convert raw value to bool, return None if unknown."""
        if value is None:
            return None

        try:
            if isinstance(value, bool):
                return bool(value)
            ival = int(value)
            return ival != 0
        except Exception:
            s = str(value).lower()
            if s in ("on", "true", "yes", "1"):
                return True
            if s in ("off", "false", "no", "0"):
                return False
        return None

    @property
    def is_on(self) -> Optional[bool]:
        """Return the current switch state as boolean, if available."""
        raw = self._read_raw()
        return self._parse_bool(raw)

    async def _send_value(self, value: bool) -> None:  # pragma: no cover - abstract
        """Send new state to the master unit. Must be implemented by subclasses."""
        raise NotImplementedError()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on and request a refresh afterwards."""
        try:
            await self._send_value(True)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "MasterSwitchBase: failed to send ON value for %s: %s",
                getattr(self, "_attr_unique_id", "?"),
                exc,
            )

        if self._REFRESH_DELAY > 0:
            await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off and request a refresh afterwards."""
        try:
            await self._send_value(False)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "MasterSwitchBase: failed to send OFF value for %s: %s",
                getattr(self, "_attr_unique_id", "?"),
                exc,
            )

        if self._REFRESH_DELAY > 0:
            await asyncio.sleep(self._REFRESH_DELAY)
        await self.coordinator.async_request_refresh()
# End Of File
