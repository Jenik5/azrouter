from __future__ import annotations

from typing import List, Optional

import logging
import asyncio

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..sensor import MasterBase  # používáme stejný základ jako master senzory

_LOGGER = logging.getLogger(__name__)


def create_master_numbers(
    client: AzRouterClient,
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
) -> List[NumberEntity]:
    """Factory pro Number entity Masteru."""
    entities: List[NumberEntity] = []

    entities.append(
        AzRouterMasterTargetPowerNumber(
            coordinator=coordinator,
            entry=entry,
            client=client,
        )
    )

    return entities


class AzRouterMasterTargetPowerNumber(MasterBase, NumberEntity):
    """Number entity pro Master regulation.target_power_w."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    _attr_native_min_value = -1000
    _attr_native_max_value = 1000
    _attr_native_step = 10

    _DEBOUNCE_SECONDS = 2.0  # po kolika sekundách nečinnosti se pošle POST

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key="master_target_power_w",
            name="Target Power",
            raw_path="settings.regulation.target_power_w",
            unit=UnitOfPower.WATT,
            devclass=None,
            entity_category=EntityCategory.CONFIG,
        )

        self._client = client
        self._value: Optional[int] = None

        # debounce stav
        self._pending_value: Optional[int] = None
        self._debounce_task: asyncio.Task | None = None

        self._attr_icon = "mdi:flash"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # inicializace z koordinátoru (coordinator.data["settings"])
        self._update_from_coordinator()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Zruš případný pending POST při odstraňování entity."""
        await super().async_will_remove_from_hass()
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

    @property
    def native_value(self) -> Optional[float]:
        return float(self._value) if self._value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Nastaví hodnotu v HA a naplánuje POST na zařízení s debounce."""
        int_value = int(round(value))

        # clamp do rozsahu
        if int_value < self._attr_native_min_value:
            int_value = int(self._attr_native_min_value)
        elif int_value > self._attr_native_max_value:
            int_value = int(self._attr_native_max_value)

        # uložíme si ji jako aktuální i pending
        self._value = int_value
        self._pending_value = int_value
        self.async_write_ha_state()

        # zrušíme případný předchozí plánovaný POST
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        async def _send_later() -> None:
            try:
                await asyncio.sleep(self._DEBOUNCE_SECONDS)
                if self._pending_value is None:
                    return
                _LOGGER.debug(
                    "AZR/number: debounced send Master target_power_w = %s",
                    self._pending_value,
                )
                await self._client.async_set_master_target_power(self._pending_value)
            except asyncio.CancelledError:
                _LOGGER.debug("AZR/number: debounced send cancelled")
            except Exception as exc:
                _LOGGER.warning(
                    "AZR/number: failed to send Master target_power_w: %s", exc
                )

        # naplánujeme nový POST do budoucna
        self._debounce_task = self.hass.loop.create_task(_send_later())

    # --- NOVÉ: čtení ze coordinator.data["settings"] ---

    def _update_from_coordinator(self) -> None:
        """Načte target_power_w z coordinator.data['settings']."""
        data = self.coordinator.data or {}
        settings = data.get("settings") or {}
        regulation = settings.get("regulation", {})

        value = regulation.get("target_power_w")

        if isinstance(value, (int, float)):
            int_value = int(value)
            if int_value < self._attr_native_min_value:
                int_value = int(self._attr_native_min_value)
            elif int_value > self._attr_native_max_value:
                int_value = int(self._attr_native_max_value)
            self._value = int_value
        else:
            self._value = None

    def _handle_coordinator_update(self) -> None:
        """Zareaguje na cyklický update koordinátoru."""
        self._update_from_coordinator()
        super()._handle_coordinator_update()
        self.async_write_ha_state()


