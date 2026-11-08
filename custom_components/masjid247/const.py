"""Constants for the Masjid 24/7 integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "masjid247"
CONF_MASJIDS: Final = "masjids"

# Prayer times come from this mirror of the Masjid 24/7 API, never from Masjid 24/7's
# own servers: one JSON file per masjid per month, refreshed every 6 hours, and filled
# on demand the first time anyone asks for a masjid.
CACHE_BASE_URL: Final = "https://prayertimes.mvppro.co.uk/jsonfiles/v1"
SETUP_URL: Final = "https://www.masjid247.com/clock/setup"

UPDATE_INTERVAL: Final = timedelta(hours=3)
RETRY_INTERVAL: Final = timedelta(minutes=30)
REQUEST_TIMEOUT: Final = 30
DEFAULT_TIMEZONE: Final = "Europe/London"
MAX_MASJIDS: Final = 10
STORAGE_VERSION: Final = 1

PRAYERS: Final = ("fajr", "dhuhr", "asr", "maghrib", "isha")
