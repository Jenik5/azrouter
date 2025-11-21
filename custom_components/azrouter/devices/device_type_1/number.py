# custom_components/azrouter/devices/device_type_1/number.py
# -----------------------------------------------------------
# Number entities for deviceType=1 (Smart Slave / boiler)
# - Target temperature
# - Boost target temperature
# - Max power (power.maxPower + settings[*].power.max)
# Uses DeviceNumberBase as a common base for device-level numbers.
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import asyncio
import copy

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature, UnitOfPower
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity import EntityCategory

from ...api import AzRouterClient
from ...const import MODEL_DEVICE_TYPE_1
from ..number import DeviceNumberBase  # ← nově používáme DeviceNumberBase

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_1 = "1"

MIN_TEMP = 20
MAX_TEMP = 85
STEP_TEMP = 5
MIN_MAXPOWER = 100
MAX_MAXPOWER = 3500
STEP_MAXPOWER = 25


def create_device_type_1_numbers(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[NumberEntity]:
    """Create number entities for all deviceType=1 devices."""

    entities: List[NumberEntity] = []

    for dev in devices:
        dev_type = str(dev.get("deviceType", ""))
        if dev_type != DEVICE_TYPE_1:
            continue

        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        dev_name = common.get("name", f"device-{dev_id}")

        if dev_id is None:
            _LOGGER.debug("Device missing common.id, skipping")
            continue

        _LOGGER.debug(
            "Creating number entities for deviceType=1 id=%s name=%s",
            dev_id,
            dev_name,
        )

        # Target temperature
        entities.append(
            DeviceType1TargetTemperatureNumber(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=dev,
                device_id=dev_id,
                key="power_target_temperature",
                name=f"{dev_name} Target Temp.",
            )
        )

        # Boost target temperature
        entities.append(
            DeviceType1TargetTemperatureBoostNumber(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=dev,
                device_id=dev_id,
                key="power_target_temperature_boost",
                name=f"{dev_name} Bst Target Temp.",
            )
        )

        # Max load power 1f
        entities.append(
            DeviceType1MaxPowerNumber(
                coordinator=coordinator,
                entry=entry,
                client=client,
                device=dev,
                device_id=dev_id,
                key="power_max",
                name=f"{dev_name} Max Power",
            )
        )

    return entities


class DeviceType1TempBase(DeviceNumberBase):
    """Shared base for temperature number entities on deviceType=1 (Smart Slave)."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = MIN_TEMP
    _attr_native_max_value = MAX_TEMP
    _attr_native_step = STEP_TEMP

    _DEBOUNCE_SECONDS = 2.0

    # set in subclasses
    _setting_key: str = ""

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
        # raw_path is empty – we do not read directly via JSON path, but via coordinator devices/settings
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path="",
            unit=UnitOfTemperature.CELSIUS,
            devclass=None,
            icon="mdi:thermometer",
            entity_category=EntityCategory.CONFIG,
            model=MODEL_DEVICE_TYPE_1,
        )

        self._client = client
        self._device_id = int(device_id)
        self._device_type = DEVICE_TYPE_1

        self._value: Optional[int] = None

        # debounce state
        self._pending_value: Optional[int] = None
        self._debounce_task: Optional[asyncio.Task] = None

    # ---------------------------------------------------------------------
    # Helpers – coordinator access
    # ---------------------------------------------------------------------

    def _clamp(self, value: int) -> int:
        if value < MIN_TEMP:
            value = MIN_TEMP
        if value > MAX_TEMP:
            value = MAX_TEMP
        # align to step
        rest = (value - MIN_TEMP) % STEP_TEMP
        if rest != 0:
            value = value - rest
        return value

    def _find_device_from_coordinator(self) -> Optional[Dict[str, Any]]:
        """Find current JSON of this device in coordinator.data['devices']."""
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

    def _update_from_coordinator(self) -> None:
        """
        Load value from
        coordinator.data['devices'][].settings[0].power[setting_key]
        into self._value.
        """
        if not self._setting_key:
            return

        dev = self._find_device_from_coordinator()
        if not dev:
            _LOGGER.debug(
                "Device_type_1 id=%s not found in coordinator devices",
                self._device_id,
            )
            return

        settings_list = dev.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            _LOGGER.debug(
                "Device_type_1 id=%s has no settings",
                self._device_id,
            )
            return

        power = settings_list[0].get("power", {})
        val = power.get(self._setting_key)

        if isinstance(val, (int, float)):
            self._value = self._clamp(int(val))
            _LOGGER.debug(
                "Loaded %s=%s for device_type_1 id=%s",
                self._setting_key,
                self._value,
                self._device_id,
            )

    # ---------------------------------------------------------------------
    # HA lifecycle
    # ---------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # load initial value from coordinator
        self._update_from_coordinator()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        await super().async_will_remove_from_hass()

    def _handle_coordinator_update(self) -> None:
        """
        Called on each coordinator refresh.
        First update self._value from coordinator.data, then let base class
        handle CoordinatorEntity logic.
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
        """Set value in HA and send to device with debounce."""
        int_val = self._clamp(int(round(value)))
        self._value = int_val
        self._pending_value = int_val
        self.async_write_ha_state()

        # cancel previous task if running
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        async def _send_later() -> None:
            try:
                await asyncio.sleep(self._DEBOUNCE_SECONDS)
                if self._pending_value is None or not self._setting_key:
                    return

                dev = self._find_device_from_coordinator()
                if not dev:
                    _LOGGER.warning(
                        "Cannot send %s for device_type_1 id=%s – device not found in coordinator",
                        self._setting_key,
                        self._device_id,
                    )
                    return

                # copy unit JSON and update settings[*].power[setting_key]
                dev_payload = copy.deepcopy(dev)
                settings_list = dev_payload.setdefault("settings", [])

                if not isinstance(settings_list, list) or not settings_list:
                    # fallback: minimal 2 entries (summer/winter)
                    settings_list = [{"power": {}}, {"power": {}}]
                    dev_payload["settings"] = settings_list

                for s in settings_list:
                    power = s.setdefault("power", {})
                    power[self._setting_key] = int(self._pending_value)

                _LOGGER.debug(
                    "Debounced send device_type_1 %s=%s (id=%s)",
                    self._setting_key,
                    self._pending_value,
                    self._device_id,
                )

                await self._client.async_post_device_settings(dev_payload)

            except asyncio.CancelledError:
                _LOGGER.debug(
                    "Debounced send cancelled for %s (id=%s)",
                    self._setting_key,
                    self._device_id,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "Failed to send device_type_1 %s (id=%s): %s",
                    self._setting_key,
                    self._device_id,
                    exc,
                )

        self._debounce_task = self.hass.loop.create_task(_send_later())


class DeviceType1TargetTemperatureNumber(DeviceType1TempBase):
    """Number for settings[*].power.targetTemperature (device_type_1)."""

    _setting_key = "targetTemperature"


class DeviceType1TargetTemperatureBoostNumber(DeviceType1TempBase):
    """Number for settings[*].power.targetTemperatureBoost (device_type_1)."""

    _setting_key = "targetTemperatureBoost"


# ---------------------------------------------------------------------------
# Max Power – reads/writes power.maxPower and syncs settings[*].power.max
# ---------------------------------------------------------------------------


class DeviceType1MaxPowerNumber(DeviceNumberBase):
    """Number for power.maxPower (device_type_1), synced to settings[*].power.max."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = MIN_MAXPOWER
    _attr_native_max_value = MAX_MAXPOWER
    _attr_native_step = STEP_MAXPOWER

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
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key=key,
            name=name,
            device=device,
            raw_path="",
            unit=UnitOfPower.WATT,
            devclass=None,
            icon="mdi:flash",
            entity_category=EntityCategory.CONFIG,
            model=MODEL_DEVICE_TYPE_1,
        )

        self._client = client
        self._device_id = int(device_id)
        self._device_type = DEVICE_TYPE_1

        self._value: Optional[int] = None
        self._pending_value: Optional[int] = None
        self._debounce_task: Optional[asyncio.Task] = None

    # ------- helpers -------

    def _clamp(self, value: int) -> int:
        if value < MIN_MAXPOWER:
            value = MIN_MAXPOWER
        if value > MAX_MAXPOWER:
            value = MAX_MAXPOWER
        # align to step
        if STEP_MAXPOWER > 0:
            rest = (value - MIN_MAXPOWER) % STEP_MAXPOWER
            if rest != 0:
                value = value - rest
        return value

    def _find_device_from_coordinator(self) -> Optional[Dict[str, Any]]:
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

    def _update_from_coordinator(self) -> None:
        dev = self._find_device_from_coordinator()
        if not dev:
            _LOGGER.debug(
                "MaxPower: device_type_1 id=%s not found in coordinator devices",
                self._device_id,
            )
            return

        power = dev.get("power", {}) or {}
        val = power.get("maxPower")

        if isinstance(val, (int, float)):
            self._value = self._clamp(int(val))
            _LOGGER.debug(
                "MaxPower: loaded maxPower=%s for device_type_1 id=%s",
                self._value,
                self._device_id,
            )

    # ------- HA lifecycle -------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._update_from_coordinator()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        await super().async_will_remove_from_hass()

    def _handle_coordinator_update(self) -> None:
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    # ------- Number API -------

    @property
    def native_value(self) -> Optional[float]:
        return float(self._value) if self._value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        int_val = self._clamp(int(round(value)))
        self._value = int_val
        self._pending_value = int_val
        self.async_write_ha_state()

        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        async def _send_later() -> None:
            try:
                await asyncio.sleep(self._DEBOUNCE_SECONDS)
                if self._pending_value is None:
                    return

                dev = self._find_device_from_coordinator()
                if not dev:
                    _LOGGER.warning(
                        "MaxPower: cannot send (id=%s) – device not found in coordinator",
                        self._device_id,
                    )
                    return

                dev_payload = copy.deepcopy(dev)

                # 1) power.maxPower
                power = dev_payload.setdefault("power", {})
                power["maxPower"] = int(self._pending_value)

                # 2) settings[*].power.max – keep in sync with actual maxPower
                settings_list = dev_payload.setdefault("settings", [])
                if not isinstance(settings_list, list):
                    settings_list = []
                    dev_payload["settings"] = settings_list

                if not settings_list:
                    # fallback: two entries if missing
                    settings_list.extend([{"power": {}}, {"power": {}}])

                for s in settings_list:
                    p = s.setdefault("power", {})
                    p["max"] = int(self._pending_value)

                _LOGGER.debug(
                    "MaxPower: debounced send maxPower=%s (id=%s)",
                    self._pending_value,
                    self._device_id,
                )

                await self._client.async_post_device_settings(dev_payload)

            except asyncio.CancelledError:
                _LOGGER.debug(
                    "MaxPower: debounced send cancelled (id=%s)",
                    self._device_id,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "MaxPower: failed to send (id=%s): %s",
                    self._device_id,
                    exc,
                )

        self._debounce_task = self.hass.loop.create_task(_send_later())

# End Of File
