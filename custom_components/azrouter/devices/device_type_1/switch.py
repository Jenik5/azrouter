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

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity import EntityCategory

from ...api import AzRouterClient
from ...const import MODEL_DEVICE_TYPE_1
from ..switch import DeviceBoostSwitch
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
    if "boost" in power:
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
                name=f"{dev_name} Boost",
                raw_path="power.boost",
            )
        )

    # ------------------------------------------------------------------
    # Block Solar Heating switch (settings[*].power.block_solar_heating)
    # ------------------------------------------------------------------
    settings_list = device.get("settings") or []
    has_block_solar = False
    if isinstance(settings_list, list):
        for s in settings_list:
            p = (s or {}).get("power", {}) or {}
            if "block_solar_heating" in p:
                has_block_solar = True
                break

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
                name=f"{dev_name} Block Solar Heating",
            )
        )

    return entities


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
        val = self._get_current_flag()
        return bool(val) if val is not None else False

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.async_set_device_type_1_power_setting(
            self._device_id,
            path="block_solar_heating",
            value=1,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.async_set_device_type_1_power_setting(
            self._device_id,
            path="block_solar_heating",
            value=0,
        )
        await self.coordinator.async_request_refresh()


# End Of File
