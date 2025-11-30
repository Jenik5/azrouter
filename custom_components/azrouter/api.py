# custom_components/azrouter/api.py
# -----------------------------------------------------------
# Central async API client for communication with A-Z Router.
# Provides unified REST helpers (_api_get/_api_post), high-level
# async methods for status, power, devices, settings, and all
# write operations including master/device boost and device settings.
# -----------------------------------------------------------

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import logging

import aiohttp

from .const import (
    API_LOGIN,
    API_STATUS,
    API_POWER,
    API_DEVICES,
    API_SETTINGS,
    API_MASTER_BOOST,
    API_DEVICE_BOOST,
    API_DEVICE_SETTINGS,
    MASTER_TARGET_POWER_MIN,
    MASTER_TARGET_POWER_MAX,
)

_LOGGER = logging.getLogger(__name__)


class AzRouterClient:
    """Async client for AZ Router API."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool = True,
    ) -> None:
        self._host = host.rstrip("/")
        self._session = session
        self._username = username or ""
        self._password = password or ""
        self._verify_ssl = verify_ssl
        self._token: Optional[str] = None

    # -------------------------------------------------------------------------
    # Interní pomocné metody
    # -------------------------------------------------------------------------

    @property
    def base(self) -> str:
        """Base URL včetně http/https prefixu."""
        return self._host if self._host.startswith("http") else f"http://{self._host}"

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _api_request(
        self,
        method: str,
        path: str,
        *,
        json: Dict[str, Any] | None = None,
    ) -> Any:
        """Unified REST call wrapper (GET/POST)."""

        url = f"{self.base}{path}"
        _LOGGER.debug("%s %s payload=%s", method, url, json)

        try:
            async with self._session.request(
                method,
                url,
                json=json,
                ssl=self._verify_ssl,
                headers=self._headers(),
            ) as resp:
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    body = await resp.text()
                    _LOGGER.warning(
                        "%s %s failed (status=%s): %s; body=%s",
                        method,
                        url,
                        resp.status,
                        e,
                        body[:300],
                    )
                    raise

                # Prefer JSON, fall back to {} on error
                try:
                    return await resp.json()
                except Exception:
                    body = await resp.text()
                    _LOGGER.debug(
                        "%s %s non-JSON response: %s",
                        method,
                        url,
                        body[:300],
                    )
                    return {}

        except Exception as exc:
            _LOGGER.warning("request %s %s failed: %s", method, url, exc)
            raise

    async def _api_get(self, path: str) -> Any:
        return await self._api_request("GET", path)

    async def _api_post(self, path: str, payload: Dict[str, Any]) -> Any:
        return await self._api_request("POST", path, json=payload)

    # -------------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------------

    async def async_login(self) -> None:
        """Authenticate and store token."""
        payload = {"data": {"username": self._username, "password": self._password}}
        data = await self._api_post(API_LOGIN, payload)

        if isinstance(data, dict):
            for key in ("token", "access_token", "accessToken", "jwt", "session"):
                val = data.get(key)
                if isinstance(val, str) and val:
                    self._token = val
                    _LOGGER.debug("stored auth token from '%s'", key)
                    break

    # Backwards compatible alias
    async def login(self) -> None:  # pragma: no cover
        _LOGGER.debug("login() deprecated, use async_login()")
        await self.async_login()

    # -------------------------------------------------------------------------
    # Basic GET endpoints
    # -------------------------------------------------------------------------

    async def async_get_status(self) -> Dict[str, Any]:
        data = await self._api_get(API_STATUS)
        return data if isinstance(data, dict) else {}

    async def async_get_power(self) -> Dict[str, Any]:
        data = await self._api_get(API_POWER)
        return data if isinstance(data, dict) else {}

    async def async_get_devices(self) -> List[Dict[str, Any]]:
        """Handles both:
        - list response
        - {"devices": [...]} response
        """
        data = await self._api_get(API_DEVICES)

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            lst = data.get("devices")
            if isinstance(lst, list):
                return lst
        return []

    async def async_get_settings(self) -> Dict[str, Any]:
        data = await self._api_get(API_SETTINGS)
        return data if isinstance(data, dict) else {}

    # Backwards compatible aliases -------------------------------------------

    async def get_status(self) -> Dict[str, Any]:  # pragma: no cover
        return await self.async_get_status()

    async def get_power(self) -> Dict[str, Any]:  # pragma: no cover
        return await self.async_get_power()

    async def async_get_devices_data(self) -> Dict[str, Any]:  # pragma: no cover
        devices = await self.async_get_devices()
        return {"devices": devices}

    async def async_get_master_settings(self) -> Dict[str, Any]:  # pragma: no cover
        return await self.async_get_settings()

    # -------------------------------------------------------------------------
    # Combined fetch for DataUpdateCoordinator
    # -------------------------------------------------------------------------

    async def async_get_all_data(self) -> Dict[str, Any]:
        """Fetch power + status + devices + settings."""
        _LOGGER.debug("async_get_all_data – start")

        tasks = [
            self.async_get_power(),
            self.async_get_status(),
            self.async_get_devices(),
            self.async_get_settings(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        r_power, r_status, r_devices, r_settings = results

        power = r_power if isinstance(r_power, dict) else {}
        status = r_status if isinstance(r_status, dict) else {}
        devices = r_devices if isinstance(r_devices, list) else []
        settings = r_settings if isinstance(r_settings, dict) else {}

        # flatten helper
        def _flatten(obj: Any, base: str, out: list) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _flatten(v, f"{base}.{k}" if base else k, out)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _flatten(v, f"{base}.{i}" if base else str(i), out)
            else:
                out.append({"path": base, "value": obj})

        master_list: List[Dict[str, Any]] = []
        _flatten(power, "power", master_list)
        _flatten(status, "status", master_list)

        return {
            "master_data": master_list,
            "devices": devices,
            "settings": settings,
        }

    # -------------------------------------------------------------------------
    # Master write operations
    # -------------------------------------------------------------------------

    async def async_set_master_boost(self, enable: bool) -> None:
        payload = {"data": {"boost": 1 if enable else 0}}
        await self._api_post(API_MASTER_BOOST, payload)

    async def async_set_master_target_power(self, target_power_w: int) -> None:
        """Writes settings.regulation.target_power_w via POST /settings."""
        try:
            value = int(target_power_w)
        except Exception:
            _LOGGER.warning("invalid target_power_w=%r", target_power_w)
            return

        # clamp using const
        if value < MASTER_TARGET_POWER_MIN:
            value = MASTER_TARGET_POWER_MIN
        elif value > MASTER_TARGET_POWER_MAX:
            value = MASTER_TARGET_POWER_MAX

        settings = await self.async_get_settings()
        regulation = settings.setdefault("regulation", {})
        regulation["target_power_w"] = value

        payload = {"data": settings}
        await self._api_post(API_SETTINGS, payload)

    # -------------------------------------------------------------------------
    # Device operations
    # -------------------------------------------------------------------------

    async def async_set_device_boost(self, device_id: int, enable: bool) -> None:
        try:
            dev_id_int = int(device_id)
        except Exception:
            _LOGGER.warning("invalid device_id=%r", device_id)
            return

        payload = {
            "data": {
                "device": {"common": {"id": dev_id_int}},
                "boost": 1 if enable else 0,
            }
        }
        await self._api_post(API_DEVICE_BOOST, payload)

    async def async_post_device_settings(self, device_payload: Dict[str, Any]) -> None:
        payload = {"data": device_payload}
        await self._api_post(API_DEVICE_SETTINGS, payload)

    # -------------------------------------------------------------------------
    # DeviceType 1 – obecná nastavení v sekci "power"/"settings[*].power"
    # -------------------------------------------------------------------------

    async def async_set_device_type_1_power_setting(
        self,
        device_id: int,
        path: str,
        value: int | float,
    ) -> None:
        """
        Obecný setter pro device_type_1 "power" nastavení.

        -   path == "maxPower":
            zapíše do root["power"]["maxPower"]
            a zároveň do settings[*].power["max"]
        -   jiné path (např. "targetTemperature", "targetTemperatureBoost",
            "block_solar_heating"):
            zapíše do settings[*].power[path] ve všech profilech (summer/winter).
        """

        DEVICE_TYPE = "1"

        # 1) načteme aktuální seznam zařízení
        try:
            devices = await self.async_get_devices()
        except Exception as exc:
            _LOGGER.warning(
                "AZR/api: async_set_device_type_1_power_setting: "
                "failed to fetch devices: %s",
                exc,
            )
            return

        if not isinstance(devices, list):
            _LOGGER.warning(
                "AZR/api: async_set_device_type_1_power_setting: "
                "invalid devices container: %r",
                devices,
            )
            return

        # 2) najdeme konkrétní device_type_1 s daným common.id
        root: Dict[str, Any] | None = None
        for dev in devices:
            try:
                dev_type = str(dev.get("deviceType"))
                common = dev.get("common", {}) or {}
                cid = int(common.get("id", -1))
            except Exception:
                continue

            if dev_type == DEVICE_TYPE and cid == device_id:
                root = dev
                break

        if not root:
            _LOGGER.warning(
                "AZR/api: async_set_device_type_1_power_setting: "
                "device_type=%s id=%s not found in devices",
                DEVICE_TYPE,
                device_id,
            )
            return

        # 3) normalizace hodnoty na int
        try:
            ival = int(round(float(value)))
        except Exception:
            _LOGGER.warning(
                "AZR/api: async_set_device_type_1_power_setting: cannot cast %r to int "
                "for device %s, path=%s",
                value,
                device_id,
                path,
            )
            return

        settings_list = root.get("settings") or []
        if not isinstance(settings_list, list):
            settings_list = []

        # 4) zápis hodnot podle typu path
        if path == "maxPower":
            # maxPower – root.power.maxPower + settings[*].power.max
            power_root = root.setdefault("power", {})
            power_root["maxPower"] = ival

            for entry in settings_list:
                p = entry.setdefault("power", {})
                p["max"] = ival

            _LOGGER.debug(
                "AZR/api: device_type_1 id=%s set power.maxPower=%s "
                "and settings[*].power.max=%s",
                device_id,
                ival,
                ival,
            )
        else:
            # ostatní – do settings[*].power[path] ve všech profilech (summer/winter)
            if not settings_list:
                _LOGGER.warning(
                    "AZR/api: async_set_device_type_1_power_setting: no settings[] "
                    "for device %s (path=%s)",
                    device_id,
                    path,
                )
                return

            for entry in settings_list:
                p = entry.setdefault("power", {})
                p[path] = ival

            _LOGGER.debug(
                "AZR/api: device_type_1 id=%s set settings[*].power.%s=%s",
                device_id,
                path,
                ival,
            )

        # 5) sestavit payload a poslat na /api/v1/device/settings
        device_payload = {
            "deviceType": DEVICE_TYPE,
            "common": root.get("common", {"id": device_id}),
            "power": root.get("power", {}),
            "settings": settings_list,
        }

        await self.async_post_device_settings(device_payload)


# End Of File
