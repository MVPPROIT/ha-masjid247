"""Parsing the mirror's files, and the time logic built on them (no Home Assistant)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.masjid247 import times
from custom_components.masjid247.api import parse_month, parse_time
from custom_components.masjid247.times import MasjidData

from .conftest import load, synth_month

LONDON = ZoneInfo("Europe/London")


def masjid(*raws: dict) -> MasjidData:
    days = {}
    for raw in raws:
        month = parse_month(raw)
        days.update(month.days)
    return MasjidData(month.masjid_id, month.name, ZoneInfo(month.timezone), days)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_parse_real_month() -> None:
    month = parse_month(load("965-2026-11.json"))
    assert month.name == "Leicester Central Mosque"
    assert month.timezone == "Europe/London"
    assert len(month.days) == 30
    day = month.days[date(2026, 11, 8)]
    assert day.begins["fajr"] == (time(5, 39),)
    assert day.jamaat["isha"] == (time(18, 30),)
    assert day.sunrise == time(7, 11)
    assert day.jummah == (time(13, 15),)
    assert day.hijri is not None and day.hijri.formatted == "28 Jumada al-Awwal 1448"
    assert day.sehri_end is None  # "" outside Ramadan


def test_parse_keeps_every_value() -> None:
    raw = synth_month(1, 2026, 11, asr={"begins": ["14:35", "15:20"], "jamaah": ["15:15"]},
                      jummah=["12:30", "13:15", "14:00"])
    day = parse_month(raw).days[date(2026, 11, 1)]
    assert day.begins["asr"] == (time(14, 35), time(15, 20))
    assert len(day.jummah) == 3


@pytest.mark.parametrize("bad", [None, [], {"days": []}, {"mosqueId": 1, "year": 2026}])
def test_parse_rejects_unusable(bad) -> None:
    with pytest.raises(ValueError):
        parse_month(bad)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("05:39", time(5, 39)), ("5:39", time(5, 39)), ("23:59", time(23, 59)),
     ("", None), ("24:00", None), ("5.39", None), (None, None), (539, None)],
)
def test_parse_time(value, expected) -> None:
    assert parse_time(value) == expected


def test_unknown_timezone_falls_back_to_london() -> None:
    raw = load("965-2026-11.json") | {"timezone": "Mars/Olympus"}
    assert parse_month(raw).timezone == "Europe/London"


def test_next_prayer_through_the_day() -> None:
    md = masjid(load("965-2026-11.json"), load("965-2026-12.json"))
    # Sunday 8 Nov 2026 (GMT, so local == UTC)
    assert times.next_prayer(md, utc("2026-11-08T05:00")).prayer == "fajr"
    event = times.next_prayer(md, utc("2026-11-08T12:00"))
    assert (event.prayer, event.when) == ("dhuhr", utc("2026-11-08T13:15"))
    assert event.begins == utc("2026-11-08T11:51")
    assert times.next_prayer(md, utc("2026-11-08T13:15")).prayer == "asr"  # at jamaat: moves on
    after_isha = times.next_prayer(md, utc("2026-11-08T18:31"))
    assert (after_isha.prayer, after_isha.when) == ("fajr", utc("2026-11-09T06:45"))


def test_friday_is_jummah() -> None:
    md = masjid(load("2093-2026-11.json"))
    event = times.next_prayer(md, utc("2026-11-13T10:00"))
    # Friday uses the Dhuhr jamaat slot (12:40 at 2093), not a guess from the list
    assert (event.prayer, event.when) == ("jummah", utc("2026-11-13T12:40"))
    # The Jummah sensor on a Sunday points at that Friday
    assert times.jummah(md, date(2026, 11, 8)) == utc("2026-11-13T12:40")
    assert times.jummah(md, date(2026, 11, 8), 1) == utc("2026-11-13T13:30")
    assert times.jummah(md, date(2026, 11, 8), 2) is None


def test_maghrib_begins_falls_back_to_jamaat() -> None:
    md = masjid(synth_month(1, 2026, 11, maghrib={"begins": [], "jamaah": ["16:24"]}))
    assert times.begins(md, date(2026, 11, 3), "maghrib") == utc("2026-11-03T16:24")
    assert times.begins(md, date(2026, 11, 3), "isha") == utc("2026-11-03T17:56")


@pytest.mark.parametrize(
    ("day", "expected_utc"),
    [
        (date(2026, 10, 24), "2026-10-24T04:39"),  # BST
        (date(2026, 10, 25), "2026-10-25T05:39"),  # clocks went back at 02:00
        (date(2027, 3, 27), "2027-03-27T05:39"),   # GMT
        (date(2027, 3, 28), "2027-03-28T04:39"),   # clocks went forward at 01:00
    ],
)
def test_clock_changes(day: date, expected_utc: str) -> None:
    md = masjid(synth_month(1, day.year, day.month))
    assert times.begins(md, day, "fajr") == utc(expected_utc)


def test_local_date_is_the_masjids_not_utc() -> None:
    md = masjid(synth_month(1, 2026, 10))
    # 23:30 UTC on 24 Oct is already 00:30 on 25 Oct in London (BST)
    assert md.local_date(utc("2026-10-24T23:30")) == date(2026, 10, 25)
    assert md.next_midnight(utc("2026-10-24T12:00")) == datetime(2026, 10, 25, tzinfo=LONDON)
