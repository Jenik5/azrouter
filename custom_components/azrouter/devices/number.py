# custom_components/azrouter/devices/number.py
# -----------------------------------------------------------
# Shared base class for device-level Number entities
#
# DeviceNumberBase:
#   - extends DeviceBase + NumberEntity
#   - keeps local value cached
#   - synchronizes value from coordinator.data on each update
#   - debounces writes to the device API
#
# Usage pattern for concrete number entities:
#   - subclass DeviceNumberBase
#   - implement:
#       _update_from_coordinator(self) -> None
#           -> read current value from coordinator.data and store into self._value
#       _clamp(self, value: float | int) -> float | int
#           -> optional: clamp / snap value to valid range (min/max/step)
#       _async_send_value(self, value: float | int) -> Awaitable[None]
#           -> actually send the value to the device via API client
# -----------------------------------------------------------

from __future__ import annotations

from typing import Optional, Any
import asyncio
import logging

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)


class DeviceNumberBase(DeviceBase, NumberEntity):
    """
    Base class for device-level numbers with:
        - coordinator-backed state,
        - local cached value,
        - debounced write to the device API.

    Subclasses MUST implement:
        -   _update_from_coordinator(self) -> None
            Read the current value from coordinator.data and store it in self._value.
        -   async _async_send_value(self, value: float | int) -> None
            Send the given value to the device (e.g. via AzRouterClient).
    Subclasses MAY override:
        -   _clamp(self, value: float | int) -> float | int
            Clamp or snap value to valid range (min/max/step).
    """

    # Default debounce delay in seconds before sending value to the device
    _DEBOUNCE_SECONDS: float = 2.0

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator,
        entry,
        key: str,
        name: str,
        device: dict[str, Any],
        raw_path: str = "",
        unit: str | None = None,
        devclass: Any | None = None,
        icon: str | None = None,
        entity_category: Any | None = None,
        model: str | None = None,
        debounce_seconds: float | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path=raw_path,
            unit=unit,
            devclass=devclass,
            icon=icon,
            entity_category=entity_category,
            model=model,
        )

        # Current numeric value (last known from coordinator or last set)
        self._value: Optional[float] = None

        # Debounce state: pending value + scheduled task
        self._pending_value: Optional[float] = None
        self._debounce_task: Optional[asyncio.Task] = None

        if debounce_seconds is not None:
            self._DEBOUNCE_SECONDS = float(debounce_seconds)

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    def _clamp(self, value: float | int) -> float | int:
        """
        Optional clamp hook.

        Subclasses can override this to enforce:
          - min / max limits,
          - step rounding, etc.

        Default: return value unchanged.
        """
        return value

    def _update_from_coordinator(self) -> None:  # pragma: no cover - abstract by convention
        """
        Read current value from coordinator.data and store it in self._value.

        Concrete subclasses MUST override this method.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _update_from_coordinator()"
        )

    async def _async_send_value(self, value: float | int) -> None:  # pragma: no cover - abstract by convention
        """
        Send the given value to the device (e.g. via AzRouterClient).

        Concrete subclasses MUST override this method.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _async_send_value()"
        )

    # ------------------------------------------------------------------
    # Home Assistant lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        # Initialize value from coordinator data
        try:
            self._update_from_coordinator()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "%s: _update_from_coordinator failed on add: %s",
                self.__class__.__name__,
                exc,
            )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up pending tasks when entity is removed."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        await super().async_will_remove_from_hass()

    def _handle_coordinator_update(self) -> None:
        """
        Called by CoordinatorEntity when coordinator data is updated.

        We:
          1) refresh self._value from coordinator.data,
          2) let the parent update the rest of the entity state.
        """
        try:
            self._update_from_coordinator()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "%s: _update_from_coordinator failed on coordinator update: %s",
                self.__class__.__name__,
                exc,
            )
        super()._handle_coordinator_update()
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # NumberEntity API
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> Optional[float]:
        """Return current numeric value."""
        return float(self._value) if self._value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """
        Set new value from HA UI and schedule a debounced write to the device.

        Steps:
          1) clamp value,
          2) update local state (_value, _pending_value),
          3) cancel any previous debounce task,
          4) schedule new debounced send.
        """
        # clamp
        try:
            clamped = self._clamp(value)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "%s: _clamp failed for value=%s: %s",
                self.__class__.__name__,
                value,
                exc,
            )
            clamped = value

        # normalize → float
        try:
            new_value = float(clamped)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "%s: cannot convert clamped value %r to float",
                self.__class__.__name__,
                clamped,
            )
            return

        self._value = new_value
        self._pending_value = new_value
        self.async_write_ha_state()

        # Cancel previous pending send, if any
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        async def _send_later() -> None:
            try:
                await asyncio.sleep(self._DEBOUNCE_SECONDS)
                if self._pending_value is None:
                    return

                send_value = self._pending_value
                _LOGGER.debug(
                    "%s: debounced send value=%s for entity_id=%s",
                    self.__class__.__name__,
                    send_value,
                    getattr(self, "entity_id", None),
                )
                await self._async_send_value(send_value)

            except asyncio.CancelledError:
                _LOGGER.debug(
                    "%s: debounced send cancelled for entity_id=%s",
                    self.__class__.__name__,
                    getattr(self, "entity_id", None),
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "%s: failed to send value for entity_id=%s: %s",
                    self.__class__.__name__,
                    getattr(self, "entity_id", None),
                    exc,
                )

        # schedule new debounced send
        self._debounce_task = self.hass.loop.create_task(_send_later())

# End Of File
