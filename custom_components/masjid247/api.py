"""Client and parser for the Masjid 24/7 prayer-time mirror.

Each file is https://masjid247.mvppro.co.uk/jsonfiles/v1/<id>/<year>/<month>.json:
the official Masjid 24/7 API's timetable for one masjid and one month, unchanged.

    {"mosqueId": 965, "name": "...", "timezone": "Europe/London", "year": 2026,
     "month": 11, "days": [{"date": "2026-11-01",
       "hijri": {"day": 21, "month": 5, "monthName": "...", "year": 1448, "formatted": "..."},
       "fajr": {"begins": ["05:28"], "jamaah": ["06:30"]}, "dhuhr": {...}, "asr": {...},
       "maghrib": {...}, "isha": {...}, "sunrise": "06:58", "sehriEnd": "",
       "zawal": "11:41", "jummah": ["13:15"]}, ...]}

Times are "HH:MM" wall-clock in the masjid's timezone; "" or [] means none.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, time
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from .const import CACHE_BASE_URL, DEFAULT_TIMEZONE, PRAYERS, REQUEST_TIMEOUT

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class Masjid247Error(Exception):
    """Base class for Masjid 24/7 errors."""


class CannotConnect(Masjid247Error):
    """The mirror could not be reached, or sent something unusable."""


class MasjidNotFound(Masjid247Error):
    """The mirror has no timetable for that masjid and month."""


class ServerBusy(Masjid247Error):
    """The mirror asked us to slow down (HTTP 429/503)."""


def parse_time(value: Any) -> time | None:
    """Parse "HH:MM" to a time, or None for blank/invalid."""
    if not isinstance(value, str):
        return None
    match = _TIME_RE.match(value.strip())
    if match is None:
        return None
    return time(int(match.group(1)), int(match.group(2)))


def _times(values: Any) -> tuple[time, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return ()
    return tuple(t for t in (parse_time(v) for v in values) if t is not None)


@dataclass(frozen=True, slots=True)
class Hijri:
    """Hijri date as the masjid publishes it."""

    day: int
    month: int
    month_name: str
    year: int
    formatted: str


@dataclass(frozen=True, slots=True)
class DayTimes:
    """One day of a masjid's timetable."""

    date: date
    begins: dict[str, tuple[time, ...]]
    jamaat: dict[str, tuple[time, ...]]
    sunrise: time | None
    sehri_end: time | None
    zawal: time | None
    jummah: tuple[time, ...]
    hijri: Hijri | None


@dataclass(frozen=True, slots=True)
class MonthTimetable:
    """One masjid, one month."""

    masjid_id: int
    name: str
    timezone: str
    year: int
    month: int
    days: dict[date, DayTimes]


def _hijri(raw: Any) -> Hijri | None:
    if not isinstance(raw, dict):
        return None
    try:
        day, month, year = int(raw["day"]), int(raw["month"]), int(raw["year"])
    except (KeyError, TypeError, ValueError):
        return None
    name = str(raw.get("monthName") or "")
    formatted = str(raw.get("formatted") or "") or f"{day} {name} {year}".strip()
    return Hijri(day, month, name, year, formatted)


def parse_month(raw: Any) -> MonthTimetable:
    """Parse one mirror file. Raises ValueError if it is not a usable timetable."""
    if not isinstance(raw, dict):
        raise ValueError("timetable is not a JSON object")
    try:
        masjid_id = int(raw["mosqueId"])
        year = int(raw["year"])
        month = int(raw["month"])
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError(f"timetable header is incomplete: {err}") from err

    tz = str(raw.get("timezone") or DEFAULT_TIMEZONE)
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        tz = DEFAULT_TIMEZONE

    days: dict[date, DayTimes] = {}
    for item in raw.get("days") or []:
        if not isinstance(item, dict):
            continue
        try:
            day = date.fromisoformat(str(item.get("date", ""))[:10])
        except ValueError:
            continue
        begins: dict[str, tuple[time, ...]] = {}
        jamaat: dict[str, tuple[time, ...]] = {}
        for prayer in PRAYERS:
            slot = item.get(prayer)
            if not isinstance(slot, dict):
                slot = {}
            begins[prayer] = _times(slot.get("begins"))
            jamaat[prayer] = _times(slot.get("jamaah"))
        days[day] = DayTimes(
            date=day,
            begins=begins,
            jamaat=jamaat,
            sunrise=parse_time(item.get("sunrise")),
            sehri_end=parse_time(item.get("sehriEnd")),
            zawal=parse_time(item.get("zawal")),
            jummah=_times(item.get("jummah")),
            hijri=_hijri(item.get("hijri")),
        )
    if not days:
        raise ValueError("timetable has no days")

    name = str(raw.get("name") or "").strip() or f"Masjid {masjid_id}"
    return MonthTimetable(masjid_id, name, tz, year, month, days)


class Masjid247Client:
    """Reads timetables from the mirror."""

    def __init__(
        self, session: aiohttp.ClientSession, base_url: str = CACHE_BASE_URL
    ) -> None:
        """Initialise with Home Assistant's shared aiohttp session."""
        self._session = session
        self._base = base_url.rstrip("/")

    async def async_get_month(
        self, masjid_id: int, year: int, month: int
    ) -> dict[str, Any]:
        """Return the raw (validated) timetable for one masjid and month."""
        url = f"{self._base}/{masjid_id}/{year}/{month}.json"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(
                    url, headers={"Accept": "application/json"}
                ) as resp:
                    if resp.status == 404:
                        raise MasjidNotFound(
                            f"no timetable for masjid {masjid_id} ({year}/{month})"
                        )
                    if resp.status in (429, 503):
                        raise ServerBusy(f"server busy (HTTP {resp.status})")
                    if resp.status != 200:
                        raise CannotConnect(f"HTTP {resp.status} from {url}")
                    raw = await resp.json(content_type=None)
        except Masjid247Error:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CannotConnect(f"{type(err).__name__}: {err}") from err

        try:
            parse_month(raw)
        except ValueError as err:
            raise CannotConnect(f"unusable timetable from {url}: {err}") from err
        return raw
