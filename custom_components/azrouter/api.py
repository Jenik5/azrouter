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


# End Of File
