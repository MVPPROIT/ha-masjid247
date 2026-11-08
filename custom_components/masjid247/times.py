"""Turn a masjid's timetable into the moments sensors show.

Pure functions over MasjidData, so they are easy to test at any date or time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .api import DayTimes
from .const import PRAYERS

FRIDAY = 4


@dataclass(slots=True)
class MasjidData:
    """Everything known about one masjid: its days across the cached months."""

    masjid_id: int
    name: str
    tz: ZoneInfo
    days: dict[date, DayTimes]

    def local_date(self, now: datetime) -> date:
        """The masjid's own calendar date at `now` (an aware datetime)."""
        return now.astimezone(self.tz).date()

    def at(self, day: date, value: time | None) -> datetime | None:
        """A wall-clock time on `day` in the masjid's timezone (handles BST/GMT)."""
        if value is None:
            return None
        return datetime.combine(day, value, tzinfo=self.tz)

    def next_midnight(self, now: datetime) -> datetime:
        """Start of the masjid's next local day."""
        tomorrow = self.local_date(now) + timedelta(days=1)
        return datetime.combine(tomorrow, time(0, 0), tzinfo=self.tz)


def nth(values: tuple[time, ...], index: int) -> time | None:
    """values[index] or None."""
    return values[index] if len(values) > index else None


def begins(md: MasjidData, day: date, prayer: str, index: int = 0) -> datetime | None:
    """When `prayer` begins on `day`.

    Many masjids leave Maghrib's start blank because it IS the jamaat time; the
    Masjid 24/7 apps show the jamaat then, and so does this.
    """
    dt = md.days.get(day)
    if dt is None:
        return None
    value = nth(dt.begins[prayer], index)
    if value is None and prayer == "maghrib" and index == 0:
        value = nth(dt.jamaat[prayer], 0)
    return md.at(day, value)


def jamaat(md: MasjidData, day: date, prayer: str, index: int = 0) -> datetime | None:
    """The jamaat (congregation) time of `prayer` on `day`."""
    dt = md.days.get(day)
    if dt is None:
        return None
    return md.at(day, nth(dt.jamaat[prayer], index))


def day_field(md: MasjidData, day: date, field: str) -> datetime | None:
    """sunrise / sehri_end / zawal on `day`."""
    dt = md.days.get(day)
    if dt is None:
        return None
    return md.at(day, getattr(dt, field))


def jummah_day(day: date) -> date:
    """The Friday on or after `day`."""
    return day + timedelta(days=(FRIDAY - day.weekday()) % 7)


def jummah(md: MasjidData, day: date, index: int = 0) -> datetime | None:
    """The `index`-th Jumu'ah sitting of the Friday on or after `day`."""
    friday = jummah_day(day)
    dt = md.days.get(friday)
    if dt is None:
        return None
    value = nth(dt.jummah, index)
    if value is None and index == 0:
        value = nth(dt.jamaat["dhuhr"], 0)
    return md.at(friday, value)


def hijri(md: MasjidData, day: date) -> str | None:
    """The masjid's Hijri date for `day`, e.g. "21 Jumada al-Awwal 1448"."""
    dt = md.days.get(day)
    if dt is None or dt.hijri is None:
        return None
    return dt.hijri.formatted


@dataclass(frozen=True, slots=True)
class PrayerEvent:
    """One prayer on one day: when it begins, its jamaat, and which one counts."""

    prayer: str                 # fajr / dhuhr / jummah / asr / maghrib / isha
    when: datetime              # jamaat, or the start when the masjid gives no jamaat
    begins: datetime | None
    jamaat: datetime | None


def day_events(md: MasjidData, day: date) -> list[PrayerEvent]:
    """The day's prayers in order. On Friday, Dhuhr is Jumu'ah.

    Friday uses the Dhuhr jamaat slot (as the Masjid 24/7 apps do: the API does not
    promise the order of the jummah list), falling back to the first Jumu'ah.
    """
    dt = md.days.get(day)
    if dt is None:
        return []
    events: list[PrayerEvent] = []
    friday = day.weekday() == FRIDAY
    for prayer in PRAYERS:
        start = begins(md, day, prayer)
        jam = jamaat(md, day, prayer)
        name = prayer
        if prayer == "dhuhr" and friday:
            name = "jummah"
            if jam is None:
                jam = md.at(day, nth(dt.jummah, 0))
        when = jam or start
        if when is not None:
            events.append(PrayerEvent(name, when, start, jam))
    return events


def next_prayer(md: MasjidData, now: datetime) -> PrayerEvent | None:
    """The next prayer whose jamaat (or start) is after `now`, today or tomorrow."""
    today = md.local_date(now)
    for day in (today, today + timedelta(days=1)):
        for event in day_events(md, day):
            if event.when > now:
                return event
    return None
