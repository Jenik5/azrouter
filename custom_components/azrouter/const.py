# custom_components/azrouter/const.py
# -----------------------------------------------------------
# Global integration constants for the AZ Router integration.
#
# - DOMAIN, NAME, platforms and config keys
# - Default scan interval
# - Shared model names and device status/type mappings
# -----------------------------------------------------------

DOMAIN = "azrouter"
NAME = "A-Z Router"

DEFAULT_SCAN_INTERVAL = 5  # seconds

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"

PLATFORMS = ["sensor", "switch", "number"]

# -----------------------------------------------------------
# Model names
# -----------------------------------------------------------

MODEL_MASTER = "A-Z Router Smart master"
MODEL_DEVICE_TYPE_1 = "A-Z Router Smart slave"
MODEL_DEVICE_TYPE_4 = "A-Z Charger"
MODEL_DEVICE_TYPE_5 = "Invertor"
MODEL_DEVICE_GENERIC = "A-Z Router Device"

# -----------------------------------------------------------
# Shared device string mappings
# -----------------------------------------------------------

DEVICE_STATUS_STRINGS = ["unpaired", "online", "offline", "error", "active"]
DEVICE_TYPE_STRINGS = ["Generic", "Power", "HDO", "Fire", "Charger", "Inverter"]

# Charger-specific mapping
CHARGE_STATUS_STRINGS = [
    "Disconnected",
    "Waiting",
    "Charging",
    "Overheated",
    "Error",
    "Unavailable",
]

# API endpoints
API_LOGIN = "/api/v1/login"
API_STATUS = "/api/v1/status"
API_POWER = "/api/v1/power"
API_DEVICES = "/api/v1/devices"
API_SETTINGS = "/api/v1/settings"
API_MASTER_BOOST = "/api/v1/system/boost"
API_DEVICE_BOOST = "/api/v1/device/boost"
API_DEVICE_SETTINGS = "/api/v1/device/settings"

# Limity pro Master target power (W) – používá api.py i master/number.py
MASTER_TARGET_POWER_MIN = -1000
MASTER_TARGET_POWER_MAX = 1000

# End Of File
