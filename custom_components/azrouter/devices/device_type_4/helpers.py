from __future__ import annotations

from typing import Any, Dict

from ...const import MODEL_DEVICE_TYPE_4

DEVICE_TYPE_4 = "4"
MODEL_NAME = MODEL_DEVICE_TYPE_4

MODE_PRIORITIZE_WHEN_CONNECTED = 0
MODE_MANUAL = 1
MODE_TIME_WINDOW = 2
MODE_HDO = 3

PHASE_OPTIONS = ["L1", "L2", "L3"]

CIRCUIT_BREAKER_LIMITS: Dict[int, int] = {
    10: 2300,
    16: 3700,
    24: 5500,
    32: 7400,
}

DEFAULT_MAX_POWER = 7400
MIN_CHARGING_POWER = 1400
CHARGING_POWER_STEP = 100

MIN_TRIGGER_POWER = 0
MAX_TRIGGER_POWER = 30000
TRIGGER_POWER_STEP = 100

MIN_TRIGGER_DURATION = 0
MAX_TRIGGER_DURATION = 3600
TRIGGER_DURATION_STEP = 1

MINUTES_MIN = 0
MINUTES_MAX = 1439
DEFAULT_SETTINGS_COUNT = 2


def _dig_value(container: Any, path: str) -> Any:
    if not path:
        return container

    cur = container
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError, TypeError):
                return None
            continue
        return None
    return cur


def has_charge_section(device: Dict[str, Any]) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        if isinstance((item or {}).get("charge"), dict):
            return True
    return False


def has_charge_setting(device: Dict[str, Any], setting_path: str) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        charge = (item or {}).get("charge", {}) or {}
        if _dig_value(charge, setting_path) is not None:
            return True
    return False


def has_mode_setting(device: Dict[str, Any], mode_id: int, setting_path: str) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        charge = (item or {}).get("charge", {}) or {}
        mode = get_mode_entry(charge, mode_id)
        if isinstance(mode, dict) and _dig_value(mode, setting_path) is not None:
            return True
    return False


def has_mode_window_setting(
    device: Dict[str, Any],
    *,
    mode_id: int,
    window_index: int,
    setting_key: str,
) -> bool:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list):
        return False
    for item in settings_list:
        charge = (item or {}).get("charge", {}) or {}
        mode = get_mode_entry(charge, mode_id)
        if not isinstance(mode, dict):
            continue
        windows = mode.get("windows") or []
        if not isinstance(windows, list) or len(windows) <= window_index:
            continue
        window = windows[window_index] or {}
        if isinstance(window, dict) and _dig_value(window, setting_key) is not None:
            return True
    return False


def find_device_from_coordinator(coordinator, device_id: int) -> Dict[str, Any] | None:
    data = coordinator.data or {}
    devices = data.get("devices") or []
    for dev in devices:
        try:
            if (
                str(dev.get("deviceType")) == DEVICE_TYPE_4
                and int(dev.get("common", {}).get("id", -1)) == int(device_id)
            ):
                return dev
        except Exception:
            continue
    return None


def get_primary_charge_settings(device: Dict[str, Any]) -> Dict[str, Any]:
    settings_list = device.get("settings") or []
    if not isinstance(settings_list, list) or not settings_list:
        return {}
    charge = settings_list[0].get("charge")
    return charge if isinstance(charge, dict) else {}


def get_mode_entry(charge_settings: Dict[str, Any], mode_id: int) -> Dict[str, Any] | None:
    modes = charge_settings.get("mode") or []
    if not isinstance(modes, list):
        return None
    for mode in modes:
        try:
            if int(mode.get("id", -1)) == int(mode_id):
                return mode
        except Exception:
            continue
    return None


def read_charge_setting(device: Dict[str, Any], setting_path: str) -> Any:
    return _dig_value(get_primary_charge_settings(device), setting_path)


def read_mode_setting(device: Dict[str, Any], mode_id: int, setting_path: str) -> Any:
    mode = get_mode_entry(get_primary_charge_settings(device), mode_id)
    if not isinstance(mode, dict):
        return None
    return _dig_value(mode, setting_path)


def read_mode_window_setting(
    device: Dict[str, Any],
    *,
    mode_id: int,
    window_index: int,
    setting_key: str,
) -> Any:
    mode = get_mode_entry(get_primary_charge_settings(device), mode_id)
    if not isinstance(mode, dict):
        return None
    windows = mode.get("windows") or []
    if not isinstance(windows, list) or len(windows) <= window_index:
        return None
    window = windows[window_index] or {}
    if not isinstance(window, dict):
        return None
    return _dig_value(window, setting_key)


def ensure_charge_settings_list(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    settings_list = payload.get("settings")
    if not isinstance(settings_list, list):
        settings_list = []
        payload["settings"] = settings_list

    if not settings_list:
        settings_list.extend({"charge": {}} for _ in range(DEFAULT_SETTINGS_COUNT))

    normalized: list[Dict[str, Any]] = []
    for item in settings_list:
        if not isinstance(item, dict):
            item = {"charge": {}}
        charge = item.get("charge")
        if not isinstance(charge, dict):
            item["charge"] = {}
        normalized.append(item)

    payload["settings"] = normalized
    return normalized


def ensure_mode_entry(charge_settings: Dict[str, Any], mode_id: int) -> Dict[str, Any]:
    modes = charge_settings.get("mode")
    if not isinstance(modes, list):
        modes = []
        charge_settings["mode"] = modes

    mode = get_mode_entry(charge_settings, mode_id)
    if mode is not None:
        return mode

    mode = {"id": int(mode_id), "enabled": 0}
    if mode_id == MODE_TIME_WINDOW:
        mode["windows"] = []
    modes.append(mode)
    return mode


def ensure_window_entry(mode: Dict[str, Any], window_index: int) -> Dict[str, Any]:
    windows = mode.get("windows")
    if not isinstance(windows, list):
        windows = []
        mode["windows"] = windows

    while len(windows) <= window_index:
        windows.append({"enabled": 1, "start": 0, "stop": 0})

    window = windows[window_index]
    if not isinstance(window, dict):
        window = {"enabled": 1, "start": 0, "stop": 0}
        windows[window_index] = window

    window.setdefault("enabled", 1)
    window.setdefault("start", 0)
    window.setdefault("stop", 0)
    return window


def set_nested_dict_value(container: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = container
    for part in parts[:-1]:
        next_value = cur.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cur[part] = next_value
        cur = next_value
    cur[parts[-1]] = value


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "on", "yes"}:
            return True
        if normalized in {"0", "false", "off", "no"}:
            return False
    return None


def read_mode_enabled(device: Dict[str, Any], mode_id: int) -> bool | None:
    return as_bool(read_mode_setting(device, mode_id, "enabled"))


def is_block_charging_enabled(device: Dict[str, Any]) -> bool:
    return as_bool(read_charge_setting(device, "block_charging")) is True


def is_block_solar_charging_enabled(device: Dict[str, Any]) -> bool:
    return as_bool(read_charge_setting(device, "block_solar_charging")) is True


def get_breaker_limit(device: Dict[str, Any] | None) -> int:
    if not isinstance(device, dict):
        return DEFAULT_MAX_POWER
    charge = device.get("charge", {}) or {}
    breaker = charge.get("circuitBreaker")
    try:
        breaker_int = int(breaker)
    except Exception:
        return DEFAULT_MAX_POWER
    return CIRCUIT_BREAKER_LIMITS.get(breaker_int, DEFAULT_MAX_POWER)
