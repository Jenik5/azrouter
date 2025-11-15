# custom_components/azrouter/devices/device_type_1/number.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import asyncio
import copy

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity import EntityCategory

from ...api import AzRouterClient
from ..sensor import DeviceBase

_LOGGER = logging.getLogger(__name__)
LOG_PREFIX = "AZR/devices/type_1/number"

DEVICE_TYPE_1 = "1"

MIN_TEMP = 20
MAX_TEMP = 85
STEP_TEMP = 5


def create_device_type_1_numbers(
    *,
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    devices: List[Dict[str, Any]],
) -> List[NumberEntity]:
    """Vytvoří number entity pro všechna zařízení deviceType=1."""

    entities: List[NumberEntity] = []

    for dev in devices:
        dev_type = str(dev.get("deviceType", ""))
        if dev_type != DEVICE_TYPE_1:
            continue

        common = dev.get("common", {}) or {}
        dev_id = common.get("id")
        dev_name = common.get("name", f"device-{dev_id}")

        if dev_id is None:
            _LOGGER.debug(
                "%s: device missing common.id, skipping", LOG_PREFIX
            )
            continue

        _LOGGER.debug(
            "%s: creating number entities for deviceType=1 id=%s name=%s",
            LOG_PREFIX,
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

    return entities

class DeviceType1TempBase(DeviceBase, NumberEntity):
    """Společný základ pro teplotní number entity u device_type_1 (Smart Slave)."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = MIN_TEMP
    _attr_native_max_value = MAX_TEMP
    _attr_native_step = STEP_TEMP

    _DEBOUNCE_SECONDS = 2.0

    # nastavené v potomcích
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
        # raw_path je prázdný – nečteme přímo z raw_path, ale z devices/settings v coordinatoru
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
            model="A-Z Router Smart slave",
        )

        self._client = client
        self._device_id = int(device_id)
        self._device_type = DEVICE_TYPE_1

        self._value: Optional[int] = None

        # debounce stav
        self._pending_value: Optional[int] = None
        self._debounce_task: Optional[asyncio.Task] = None

    # ---------------------------------------------------------------------
    # Pomocné metody pro čtení z coordinator.data
    # ---------------------------------------------------------------------

    def _clamp(self, value: int) -> int:
        if value < MIN_TEMP:
            value = MIN_TEMP
        if value > MAX_TEMP:
            value = MAX_TEMP
        # zarovnání na krok
        rest = (value - MIN_TEMP) % STEP_TEMP
        if rest != 0:
            value = value - rest
        return value

    def _find_device_from_coordinator(self) -> Optional[Dict[str, Any]]:
        """Najde aktuální JSON daného device v coordinator.data['devices']."""
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
        Načte hodnotu z coordinator.data['devices'][].settings[0].power[setting_key]
        a uloží ji do self._value.
        """
        if not self._setting_key:
            return

        dev = self._find_device_from_coordinator()
        if not dev:
            _LOGGER.debug(
                "%s: device_type_1 id=%s not found in coordinator devices",
                LOG_PREFIX,
                self._device_id,
            )
            return

        settings_list = dev.get("settings") or []
        if not isinstance(settings_list, list) or not settings_list:
            _LOGGER.debug(
                "%s: device_type_1 id=%s has no settings",
                LOG_PREFIX,
                self._device_id,
            )
            return

        power = settings_list[0].get("power", {})
        val = power.get(self._setting_key)

        if isinstance(val, (int, float)):
            self._value = self._clamp(int(val))
            _LOGGER.debug(
                "%s: loaded %s=%s for device_type_1 id=%s",
                LOG_PREFIX,
                self._setting_key,
                self._value,
                self._device_id,
            )

    # ---------------------------------------------------------------------
    # HA lifecycle
    # ---------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # při přidání entity hned zkusíme načíst hodnotu z aktuálních dat koordinátoru
        self._update_from_coordinator()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        await super().async_will_remove_from_hass()

    def _handle_coordinator_update(self) -> None:
        """
        Volá se při každém refreshi koordinátoru.
        Nejprve aktualizujeme self._value z coordinator.data, pak necháme základ
        (DeviceBase/CoordinatorEntity) přepsat stav entity.
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
        """Nastaví hodnotu v HA a s debounce ji pošle na zařízení."""
        int_val = self._clamp(int(round(value)))
        self._value = int_val
        self._pending_value = int_val
        self.async_write_ha_state()

        # zrušit případný předchozí task
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
                        "%s: cannot send %s for device_type_1 id=%s – device not found in coordinator",
                        LOG_PREFIX,
                        self._setting_key,
                        self._device_id,
                    )
                    return

                # uděláme kopii JSONu jednotky a upravíme settings[*].power[setting_key]
                dev_payload = copy.deepcopy(dev)
                settings_list = dev_payload.setdefault("settings", [])

                if not isinstance(settings_list, list) or not settings_list:
                    # fallback: dvě sady (summer/winter) jako minimální varianta
                    settings_list = [{"power": {}}, {"power": {}}]
                    dev_payload["settings"] = settings_list

                for s in settings_list:
                    power = s.setdefault("power", {})
                    power[self._setting_key] = int(self._pending_value)

                _LOGGER.debug(
                    "%s: debounced send device_type_1 %s=%s (id=%s)",
                    LOG_PREFIX,
                    self._setting_key,
                    self._pending_value,
                    self._device_id,
                )

                await self._client.async_post_device_settings(dev_payload)

            except asyncio.CancelledError:
                _LOGGER.debug(
                    "%s: debounced send cancelled for %s (id=%s)",
                    LOG_PREFIX,
                    self._setting_key,
                    self._device_id,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "%s: failed to send device_type_1 %s (id=%s): %s",
                    LOG_PREFIX,
                    self._setting_key,
                    self._device_id,
                    exc,
                )

        self._debounce_task = self.hass.loop.create_task(_send_later())


class DeviceType1TargetTemperatureNumber(DeviceType1TempBase):
    """Number pro settings[*].power.targetTemperature (device_type_1)."""
    _setting_key = "targetTemperature"


class DeviceType1TargetTemperatureBoostNumber(DeviceType1TempBase):
    """Number pro settings[*].power.targetTemperatureBoost (device_type_1)."""
    _setting_key = "targetTemperatureBoost"
