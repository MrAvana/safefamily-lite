"""Constants for the SafeFamily Lite integration."""

DOMAIN = "safefamily_lite"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_SCAN_INTERVAL = "scan_interval"

REGIONS = {
    "EU": "https://skills.apps.elari.tech/",
    "RU": "https://skills.apps.elari.systems/",
}

DEVICE_BASE = "https://appapi.ru-watch.com/"
ECP_BASE = "https://skills.apps.elari.tech/"

APEX_APP_ID = "111"
API_KEY = "debug"
SIGNING_SECRET = "7A2CBA15-0FEA-41BB-8628-90CEA11A94CA1"
PKG_NAME = "com.apex"
PKG_VERSION = "android-105"

DEFAULT_SCAN_INTERVAL = 300
DEFAULT_OFFLINE_AFTER_MIN = 120

# Command codes used by multiple platforms
CMD_STEP_GOAL = "1508"

# Friendly watch names keyed by the API "Type" code. Extend as needed; the
# device info sensor falls back to the raw code when a type is not listed.
MODEL_NAMES = {
    "RU_K01": "FixiTime Fun",
    "RU_K03": "KidPhone Bubble",
}