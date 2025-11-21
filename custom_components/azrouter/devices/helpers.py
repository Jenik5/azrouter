# custom_components/azrouter/devices/helpers.py
# -----------------------------------------------------------
# Helper utilities shared across device and master entities.
#
# - _dig: nested dictionary navigation using dot-notation
# - _get_value: unified lookup into coordinator data (status/power/settings)
# - find_device_by_id: locate device entry in /devices payload by common.id
# -----------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _dig(d: Dict[str, Any], path: str) -> Any:
    """Traverse a nested dict using a dot-separated path."""
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _get_value(
    payload: Dict[str, Any],
    path: str,
    extra_roots: Optional[Iterable[str]] = None,
) -> Any:
    """
    Try to get a value from a coordinator payload.

    Search order:
        1) Directly in payload (works for raw /status, /power, /settings payloads).
        2) In well-known sub-roots: "status", "power", "settings".
        3) In any additional roots passed via extra_roots.

    This helper is intended for dict-based master payloads, not for per-device
    structures in /devices responses.
    """
    if not isinstance(payload, dict):
        return None

    # 1) direct lookup
    value = _dig(payload, path)
    if value is not None:
        return value

    # 2) known roots
    for root_key in ("status", "power", "settings"):
        root = payload.get(root_key)
        if isinstance(root, dict):
            value = _dig(root, path)
            if value is not None:
                return value

    # 3) optional extra roots (for future extensions)
    if extra_roots:
        for root_key in extra_roots:
            root = payload.get(root_key)
            if isinstance(root, dict):
                value = _dig(root, path)
                if value is not None:
                    return value

    return None


def find_device_by_id(devices: List[Dict[str, Any]], device_id: int) -> Optional[Dict[str, Any]]:
    """
    Find a device entry in /devices payload by its common.id.

    Returns the device dict or None if not found.
    """
    for dev in devices:
        common = dev.get("common")
        if isinstance(common, dict) and common.get("id") == device_id:
            return dev
    return None
# End Of File
