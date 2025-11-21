# custom_components/azrouter/devices/master/switch.py
# -----------------------------------------------------------
# Master-level switch entities for the AZ Router integration.
#
# - async_create_entities:
#     Factory for all master switches.
#
# - AzRouterMasterBoostSwitch:
#     Switch exposing status.system.masterBoost on the master unit.
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, List
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...api import AzRouterClient
from ..switch import MasterSwitchBase

_LOGGER = logging.getLogger(__name__)


async def async_create_entities(
    coordinator: DataUpdateCoordinator,
    entry: ConfigEntry,
    client: AzRouterClient,
) -> List[SwitchEntity]:
    """Create master switch entities (currently only Master Boost)."""

    entities: List[SwitchEntity] = []

    _LOGGER.debug("master.switch: creating Master Boost switch")

    entities.append(
        AzRouterMasterBoostSwitch(
            coordinator=coordinator,
            entry=entry,
            client=client,
        )
    )

    return entities


class AzRouterMasterBoostSwitch(MasterSwitchBase):
    """Switch representing 'status.system.masterBoost' on the master unit."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        client: AzRouterClient,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            key="master_boost",
            name="Master Boost",
            raw_path="status.system.masterBoost",
            icon="mdi:flash-outline",
        )
        self._client = client

    async def _send_value(self, value: bool) -> None:
        """Send new boost state to the master unit via API."""
        if self._client is None:
            _LOGGER.error(
                "AzRouterMasterBoostSwitch: cannot send value %s, client is None",
                value,
            )
            return

        try:
            await self._client.async_set_master_boost(value)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "AzRouterMasterBoostSwitch: async_set_master_boost(%s) failed: %s",
                value,
                exc,
            )
# End Of File
