# custom_components/azrouter/devices/device_type_4/number.py
# -----------------------------------------------------------
# Number entities for deviceType=4 (Wallbox / Charger)
# - Manual charging power for "manual" mode (mode.id == 1)
# - Min/max are dynamically limited by the circuit breaker value
#   reported in charge.circuitBreaker
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import asyncio
import copy

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfPower
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_4 = "4"

# Circuit breaker → max allowed manual charging power [W]
CIRCUIT_BREAKER_LIMITS: Dict[int, int] = {
    10: 2300,
    16: 3700,
    24: 5500,
    32: 7400,
}

DEFAULT_MAX_POWER = 7400       # fallback when circuitBreaker is unknown
MIN_MANUAL_POWER = 1400             
STEP_MANUAL_POWER = 100        # step in W for the number entity

# mode.id which represents "manual charging" mode in settings.charge.mode[*]
MANUAL_MODE_ID = 1


def create_device_type_4_numbers(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[NumberEntity]:
    """Create number entities for all deviceType=4 devices."""

    entities: List[NumberEntity] = []

    for dev in devices:
        dev_type = str(dev.get("deviceType", ""))
        if dev_type != DEVICE_TYPE_4:
            continue

        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        dev_name = common.get("name", f"device-{dev_id}")

        if dev_id is None:
            _LOGGER.debug(
                "create_device_type_4_numbers: device missing common.id, skipping"
            )
            continue

        _LOGGER.debug(
            "create_device_type_4_numbers: creating number entities for deviceType=4 id=%s name=%s",
            dev_id,
            dev_name,
        )

        entities.append(
            DeviceType4ManualChargingPowerNumber(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=dev,
                device_id=int(dev_id),
                key="charge_manual_power",
                name=f"{dev_name} Manual Power",
            )
        )

    return entities


class DeviceType4ManualChargingPowerNumber(DeviceBase, NumberEntity):
    """
    Number entity for manual charging power (deviceType=4, Wallbox).

    Backed by settings[*].charge.mode[id == MANUAL_MODE_ID].power

    - Reads current value from coordinator.data["devices"]
    - Writes value via POST /api/v1/device/settings
    - Min/max are dynamically adjusted according to charge.circuitBreaker
    """

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = MIN_MANUAL_POWER
    _attr_native_max_value = DEFAULT_MAX_POWER
    _attr_native_step = STEP_MANUAL_POWER

    _DEBOUNCE_SECONDS = 2.0

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
        # raw_path is empty – we do not read directly via DeviceBase._read_raw(),
        # but via devices/settings in coordinator.data
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path="",
            unit=UnitOfPower.WATT,
            devclass=None,
            icon="mdi:ev-station",
            entity_category=EntityCategory.CONFIG,
            model="A-Z Charger",
        )

        self._client = client
        self._device_id = int(device_id)
        self._device_type = DEVICE_TYPE_4

        self._value: Optional[int] = None
        self._pending_value: Optional[int] = None
        self._debounce_task: Optional[asyncio.Task] = None

    # ---------------------------------------------------------------------
    # Helper methods to work with coordinator.data
    # ---------------------------------------------------------------------

    def _find_device_from_coordinator(self) -> Optional[Dict[str, Any]]:
        """Find the current JSON of this device in coordinator.data['devices']."""
        data = self.coordinator.data or {}
        devices = data.get("devices") or []

        for dev in devices:
            try:
                if (
                    str(dev.get("deviceType")) == self._device_type
                    and dev.get("common", {}).get("id") == self._device_id
                ):
                    return dev
            except Exception:
                continue

        return None

    def _get_breaker_limit(self, dev: Optional[Dict[str, Any]]) -> int:
        """
        Get max allowed power (W) based on charge.circuitBreaker.

        If the breaker value is unknown or not mapped, DEFAULT_MAX_POWER is used.
        """
        if not dev:
            return DEFAULT_MAX_POWER

        charge = dev.get("charge", {}) or {}
        breaker = charge.get("circuitBreaker")

        try:
            breaker_int = int(breaker)
        except Exception:
            return DEFAULT_MAX_POWER

        limit = CIRCUIT_BREAKER_LIMITS.get(breaker_int)
        if limit is None:
            return DEFAULT_MAX_POWER

        return limit

    def _clamp(self, value: int, max_limit: int) -> int:
        """
        Clamp value into [MIN_MANUAL_POWER, max_limit] and align to STEP_MANUAL_POWER.
        """
        if value < MIN_MANUAL_POWER:
            value = MIN_MANUAL_POWER
        if value > max_limit:
            value = max_limit

        if STEP_MANUAL_POWER > 0:
            rest = (value - MIN_MANUAL_POWER) % STEP_MANUAL_POWER
            if rest != 0:
                value = value - rest

        return value

    def _update_from_coordinator(self) -> None:
        """
        Load current manual charging power from coordinator.data and update self._value.

        Source:
          devices[*] (matching deviceType=4 & common.id)
            → settings[0].charge.mode[id == MANUAL_MODE_ID].power
        """
        dev = self._find_device_from_coordinator()
        if not dev:
            _LOGGER.debug(
                "DeviceType4ManualChargingPowerNumber: device id=%s not found in coordinator devices",
                self._device_id,
            )
            return

        max_limit = self._get_breaker_limit(dev)
        self._attr_native_max_value = float(max_limit)

        settings_list = dev.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            _LOGGER.debug(
                "DeviceType4ManualChargingPowerNumber: device id=%s has no settings",
                self._device_id,
            )
            return

        # Use the first settings entry as primary (same pattern as device_type_1)
        charge_settings = settings_list[0].get("charge", {})
        modes = charge_settings.get("mode") or []

        manual_power = None
        if isinstance(modes, list):
            for m in modes:
                if m.get("id") == MANUAL_MODE_ID:
                    manual_power = m.get("power")
                    break

        if isinstance(manual_power, (int, float)):
            val = self._clamp(int(manual_power), max_limit)
            self._value = val
            _LOGGER.debug(
                "DeviceType4ManualChargingPowerNumber: loaded manual power=%s W for device id=%s (max_limit=%s)",
                self._value,
                self._device_id,
                max_limit,
            )

    # ---------------------------------------------------------------------
    # HA lifecycle
    # ---------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        self._update_from_coordinator()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending debounced POST when entity is removed."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        await super().async_will_remove_from_hass()

    def _handle_coordinator_update(self) -> None:
        """
        Called on every coordinator refresh.

        First update self._value from coordinator.data, then let DeviceBase/CoordinatorEntity
        update the entity state in HA.
        """
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    # ---------------------------------------------------------------------
    # Number API
    # ---------------------------------------------------------------------

    @property
    def native_value(self) -> Optional[float]:
        return float(self._value) if self._value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """
        Set the value in HA, then send it to the device with debounce.

        The value is clamped to the current breaker limit (dynamic max).
        """
        dev = self._find_device_from_coordinator()
        max_limit = self._get_breaker_limit(dev)
        self._attr_native_max_value = float(max_limit)

        int_val = self._clamp(int(round(value)), max_limit)
        self._value = int_val
        self._pending_value = int_val
        self.async_write_ha_state()

        # Cancel any previous scheduled POST
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        async def _send_later() -> None:
            try:
                await asyncio.sleep(self._DEBOUNCE_SECONDS)
                if self._pending_value is None:
                    return

                dev_current = self._find_device_from_coordinator()
                if not dev_current:
                    _LOGGER.warning(
                        "DeviceType4ManualChargingPowerNumber: cannot send manual power for device id=%s – device not found in coordinator",
                        self._device_id,
                    )
                    return

                dev_payload = copy.deepcopy(dev_current)
                settings_list = dev_payload.setdefault("settings", [])

                if not isinstance(settings_list, list) or not settings_list:
                    # Fallback: create two settings entries if they are missing
                    settings_list.extend(
                        [
                            {"charge": {"mode": []}},
                            {"charge": {"mode": []}},
                        ]
                    )

                for s in settings_list:
                    charge = s.setdefault("charge", {})
                    modes = charge.setdefault("mode", [])

                    # Ensure there is a manual mode entry with id == MANUAL_MODE_ID
                    manual_entry = None
                    if isinstance(modes, list):
                        for m in modes:
                            if m.get("id") == MANUAL_MODE_ID:
                                manual_entry = m
                                break

                    if manual_entry is None:
                        manual_entry = {"id": MANUAL_MODE_ID, "enabled": 1}
                        modes.append(manual_entry)

                    manual_entry["power"] = int(self._pending_value)

                _LOGGER.debug(
                    "DeviceType4ManualChargingPowerNumber: debounced send manual power=%s W (device id=%s)",
                    self._pending_value,
                    self._device_id,
                )

                await self._client.async_post_device_settings(dev_payload)

            except asyncio.CancelledError:
                _LOGGER.debug(
                    "DeviceType4ManualChargingPowerNumber: debounced send cancelled (device id=%s)",
                    self._device_id,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "DeviceType4ManualChargingPowerNumber: failed to send manual power (device id=%s): %s",
                    self._device_id,
                    exc,
                )

        self._debounce_task = self.hass.loop.create_task(_send_later())

# End Of File
