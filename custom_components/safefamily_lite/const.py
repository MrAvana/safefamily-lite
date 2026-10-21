"""Constants for the SafeFamily Lite integration."""

DOMAIN = "safefamily_lite"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_LOCAL_URL = "local_url"
CONF_LOCAL_NAME = "local_name"

# A private server on the LAN costs nothing to poll, so the default is
# snappier than the old cloud's. The watch itself reports roughly every
# 2.5 minutes, so anything below ~60 s only re-reads the same value.
DEFAULT_LOCAL_SCAN_INTERVAL = 60

# A watch that is alive sends a heartbeat every ~5 minutes, so three misses in
# a row mean it is gone (out of coverage, flat battery, SIM trouble).
LOCAL_OFFLINE_AFTER_MIN = 15
