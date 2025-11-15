from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional
import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

LOGIN_PATH   = "/api/v1/login"
STATUS_PATH  = "/api/v1/status"
POWER_PATH   = "/api/v1/power"
DEVICES_PATH = "/api/v1/devices"
SETTINGS_PATH = "/api/v1/settings"
BOOST_PATH   = "/api/v1/system/boost"
DEVICE_BOOST_PATH = "/api/v1/device/boost"
DEVICE_SETTINGS_PATH = "/api/v1/device/settings"


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

    @property
    def base(self) -> str:
        return self._host if self._host.startswith("http") else f"http://{self._host}"

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # -------------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------------

    async def login(self) -> None:
        """Authenticate and store token if returned."""
        url = f"{self.base}{LOGIN_PATH}"
        payload = {"data": {"username": self._username, "password": self._password}}
        _LOGGER.debug("POST login -> %s", url)

        async with self._session.post(url, json=payload, ssl=self._verify_ssl) as resp:
            resp.raise_for_status()

            try:
                data = await resp.json()
            except Exception:
                data = {}

            _LOGGER.debug("Login response: %s", data)
            for key in ("token", "access_token", "accessToken", "jwt", "session"):
                if key in data and isinstance(data[key], str):
                    self._token = data[key]
                    _LOGGER.debug("Stored auth token from key: %s", key)
                    break

    # -------------------------------------------------------------------------
    # Základní GET endpointy
    # -------------------------------------------------------------------------

    async def get_status(self) -> Dict[str, Any]:
        url = f"{self.base}{STATUS_PATH}"
        _LOGGER.debug("GET %s", url)
        async with self._session.get(url, ssl=self._verify_ssl, headers=self._headers()) as resp:
            resp.raise_for_status()
            try:
                return await resp.json()
            except Exception:
                text = await resp.text()
                _LOGGER.debug("Status not JSON, raw: %s", text[:200])
                return {}

    async def get_power(self) -> Dict[str, Any]:
        url = f"{self.base}{POWER_PATH}"
        _LOGGER.debug("GET %s", url)
        async with self._session.get(url, ssl=self._verify_ssl, headers=self._headers()) as resp:
            resp.raise_for_status()
            try:
                return await resp.json()
            except Exception:
                text = await resp.text()
                _LOGGER.debug("Power not JSON, raw: %s", text[:200])
                return {}

    async def async_get_devices_data(self) -> Dict[str, Any]:
        """
        Načte /api/v1/devices.

        Očekáváme list zařízení, proto ho zabalíme do struktury {"devices": [...]}.
        """
        url = f"{self.base}{DEVICES_PATH}"
        _LOGGER.debug("AZR/api: GET %s", url)

        async with self._session.get(url, ssl=self._verify_ssl, headers=self._headers()) as resp:
            _LOGGER.debug("AZR/api: HTTP status: %s", resp.status)

            try:
                json_data = await resp.json()
                _LOGGER.debug("AZR/api: raw JSON response type: %s", type(json_data))
                _LOGGER.debug("AZR/api: raw JSON response: %s", json_data)

                devices = json_data  # endpoint zřejmě vrací rovnou list
                _LOGGER.debug(
                    "AZR/api: extracted devices list (len=%s): %s",
                    len(devices) if isinstance(devices, list) else "not-a-list",
                    devices,
                )

                return {"devices": devices}

            except Exception as e:
                text = await resp.text()
                _LOGGER.debug("AZR/api: response was not JSON! Error: %s", e)
                _LOGGER.debug("AZR/api: raw response text: %s", text[:300])

                return {"devices": []}

    async def async_get_master_settings(self) -> Dict[str, Any]:
        """Fetch full Master settings JSON from /api/v1/settings."""
        url = f"{self.base}{SETTINGS_PATH}"
        _LOGGER.debug("AZR/api: GET Master settings -> %s", url)

        async with self._session.get(
            url,
            ssl=self._verify_ssl,
            headers=self._headers(),
        ) as resp:
            _LOGGER.debug("AZR/api: Master settings HTTP status: %s", resp.status)
            resp.raise_for_status()

            try:
                json_data = await resp.json()
                _LOGGER.debug("AZR/api: Master settings JSON: %s", json_data)
                return json_data
            except Exception as e:
                text = await resp.text()
                _LOGGER.debug(
                    "AZR/api: Master settings not JSON! Error: %s, text: %s",
                    e,
                    text[:300],
                )
                return {}

    # -------------------------------------------------------------------------
    # Kombinovaný update pro DataUpdateCoordinator
    # -------------------------------------------------------------------------

    async def async_get_all_data(self) -> Dict[str, Any]:
        """Fetch /api/v1/power, /api/v1/status, /api/v1/devices a /api/v1/settings a vrátí kombinovaná data."""

        _LOGGER.debug("AZR/api: Fetching power + status (parallel)")

        power_t = asyncio.create_task(self.get_power())
        status_t = asyncio.create_task(self.get_status())

        power = None
        status = None

        try:
            results = await asyncio.gather(power_t, status_t, return_exceptions=True)
            r_power, r_status = results

            if isinstance(r_power, Exception):
                _LOGGER.debug("AZR/api: async_get_all_data: get_power raised: %s", r_power)
            else:
                power = r_power

            if isinstance(r_status, Exception):
                _LOGGER.debug("AZR/api: async_get_all_data: get_status raised: %s", r_status)
            else:
                status = r_status

        except Exception as exc:
            _LOGGER.debug("AZR/api: async_get_all_data: gather failed, trying individually: %s", exc)
            try:
                power = await power_t
            except Exception as e2:
                _LOGGER.debug("async_get_all_data: get_power individually failed: %s", e2)
                power = None
            try:
                status = await status_t
            except Exception as e3:
                _LOGGER.debug("async_get_all_data: get_status individually failed: %s", e3)
                status = None

        # flatten helper
        def _flatten_to_list(obj: Any, base: str, out: list):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_base = f"{base}.{k}" if base else k
                    _flatten_to_list(v, new_base, out)
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    new_base = f"{base}.{idx}" if base else str(idx)
                    _flatten_to_list(item, new_base, out)
            else:
                out.append({"path": base, "value": obj})

        master_list: list[Dict[str, Any]] = []

        if isinstance(power, dict):
            _flatten_to_list(power, "power", master_list)

        if isinstance(status, dict):
            _flatten_to_list(status, "status", master_list)

        _LOGGER.debug("async_get_all_data produced %d items", len(master_list))
        if master_list:
            _LOGGER.debug("async_get_all_data sample: %s", master_list[:5])

        # ---- devices ----
        devices_list: list[Dict[str, Any]] = []
        try:
            devices_result = await self.async_get_devices_data()
            if isinstance(devices_result, dict):
                candidate = devices_result.get("devices", [])
            else:
                candidate = devices_result

            if isinstance(candidate, (list, tuple)):
                devices_list = list(candidate)
            _LOGGER.debug("AZR/api: async_get_all_data: fetched %d devices", len(devices_list))
        except Exception as exc:
            _LOGGER.debug("AZR/api: async_get_all_data: failed to fetch devices: %s", exc)
            devices_list = []

        # ---- master settings (pro master number Target Power) ----
        settings: Dict[str, Any] = {}
        try:
            settings = await self.async_get_master_settings()
        except Exception as exc:
            _LOGGER.debug("AZR/api: async_get_all_data: failed to fetch settings: %s", exc)
            settings = {}

        return {
            "master_data": master_list,
            "devices": devices_list,
            "settings": settings,
        }

    # -------------------------------------------------------------------------
    # Master ovládání
    # -------------------------------------------------------------------------

    async def async_set_master_boost(self, enable: bool) -> None:
        """Turn Master Boost ON/OFF."""
        url = f"{self.base}{BOOST_PATH}"
        payload = {"data": {"boost": 1 if enable else 0}}
        _LOGGER.debug("POST boost -> %s payload=%s", url, payload)

        async with self._session.post(url, json=payload, ssl=self._verify_ssl, headers=self._headers()) as resp:
            resp.raise_for_status()

    async def async_set_master_target_power(self, target_power_w: int) -> None:
        """Set Master regulation.target_power_w via /api/v1/settings."""

        # clamp
        clamped = max(-1000, min(1000, int(target_power_w)))
        if clamped != target_power_w:
            _LOGGER.debug(
                "AZR/api: Master target_power_w %s out of range, clamped to %s",
                target_power_w,
                clamped,
            )

        # 1) read current settings
        settings = await self.async_get_master_settings()
        if not isinstance(settings, dict) or not settings:
            _LOGGER.warning(
                "AZR/api: async_set_master_target_power: invalid settings: %s",
                settings,
            )
            return

        # 2) modify regulation.target_power_w
        regulation = settings.setdefault("regulation", {})
        regulation["target_power_w"] = clamped

        # 3) send POST
        payload = {"data": settings}
        url = f"{self.base}{SETTINGS_PATH}"

        _LOGGER.debug(
            "AZR/api: POST Master settings update -> %s (target_power_w=%s)",
            url,
            clamped,
        )

        async with self._session.post(
            url,
            json=payload,
            ssl=self._verify_ssl,
            headers=self._headers(),
        ) as resp:
            _LOGGER.debug(
                "AZR/api: POST Master settings HTTP status: %s", resp.status
            )
            resp.raise_for_status()

    # -------------------------------------------------------------------------
    # Device ovládání (boost + settings)
    # -------------------------------------------------------------------------

    async def async_set_device_boost(self, device_id: int, enable: bool) -> None:
        """Turn Boost ON/OFF for a specific device (by common.id)."""
        url = f"{self.base}{DEVICE_BOOST_PATH}"
        payload = {
            "data": {
                "device": {
                    "common": {
                        "id": int(device_id),
                    }
                },
                "boost": 1 if enable else 0,
            }
        }

        _LOGGER.debug(
            "AZR/api: POST device boost -> %s payload=%s",
            url,
            payload,
        )

        async with self._session.post(
            url,
            json=payload,
            ssl=self._verify_ssl,
            headers=self._headers(),
        ) as resp:
            text = await resp.text()
            _LOGGER.debug(
                "AZR/api: device boost response status=%s body=%s",
                resp.status,
                text[:200],
            )
            resp.raise_for_status()

    async def async_post_device_settings(self, device_payload: Dict[str, Any]) -> None:
        """
        Pošle kompletní JSON jedné jednotky na /api/v1/device/settings.

        Očekává, že device_payload má strukturu:
        {
            "deviceType": "...",
            "common": {..., "id": ...},
            "power": {...},
            "settings": [...]
        }
        a my ho zabalíme do {"data": device_payload}.
        """
        url = f"{self.base}{DEVICE_SETTINGS_PATH}"
        payload = {"data": device_payload}

        _LOGGER.debug(
            "AZR/api: POST device settings -> %s payload=%s",
            url,
            payload,
        )

        async with self._session.post(
            url,
            json=payload,
            ssl=self._verify_ssl,
            headers=self._headers(),
        ) as resp:
            text = await resp.text()
            _LOGGER.debug(
                "AZR/api: POST device settings response status=%s body=%s",
                resp.status,
                text[:300],
            )
            resp.raise_for_status()
