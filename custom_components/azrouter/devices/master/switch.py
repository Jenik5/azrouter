# custom_components/azrouter/devices/master/switch.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..sensor import MasterBase  # společný základ pro master entity

_LOGGER = logging.getLogger(__name__)


async def async_create_entities(
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    client: AzRouterClient,
) -> List[SwitchEntity]:
    """Vytvoří master switche (zatím jen Master Boost)."""

    entities: List[SwitchEntity] = []

    _LOGGER.debug("AZR/master_switch: creating Master Boost switch")

    entities.append(
        AzRouterMasterBoostSwitch(
            coordinator=coordinator,
            entry=entry,
            client=client,
        )
    )

    return entities


class AzRouterMasterBoostSwitch(MasterBase, SwitchEntity):
    """Switch reprezentující 'status.system.masterBoost' na master jednotce."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
    ) -> None:
        # MasterBase → správné unique_id + device_info (Master zařízení)
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key="master_boost",
            name="Master Boost",
            raw_path="status.system.masterBoost",
            unit=None,
            devclass=None,
        )

        self._client = client
        self._attr_icon = "mdi:flash-outline"

    # ------------------------------------------------------------------ #
    # ČTENÍ STAVU
    # ------------------------------------------------------------------ #

    @property
    def is_on(self) -> Optional[bool]:
        """Aktuální stav boostu podle coordinator.data['master_data']."""
        data: Dict[str, Any] = self.coordinator.data or {}
        master = data.get("master_data", [])

        val = None
        if isinstance(master, list):
            for item in master:
                if item.get("path") == "status.system.masterBoost":
                    val = item.get("value")
                    break

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

    # ------------------------------------------------------------------ #
    # ZÁPIS – HA API
    # ------------------------------------------------------------------ #

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Zapne Master Boost."""
        _LOGGER.debug("AZR/master_switch: turning ON Master Boost via API")
        try:
            await self._client.async_set_master_boost(True)
        except Exception as exc:
            _LOGGER.error("AZR/master_switch: async_set_master_boost(True) failed: %s", exc)
        # po zápisu si vyžádáme refresh – stav se dorovná z /status
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Vypne Master Boost."""
        _LOGGER.debug("AZR/master_switch: turning OFF Master Boost via API")
        try:
            await self._client.async_set_master_boost(False)
        except Exception as exc:
            _LOGGER.error("AZR/master_switch: async_set_master_boost(False) failed: %s", exc)
        await self.coordinator.async_request_refresh()
