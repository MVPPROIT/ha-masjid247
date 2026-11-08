"""Sensors end to end: values, ticks at jamaat and midnight, month end, clock changes,
and keeping times when the server is down."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.masjid247.diagnostics import async_get_config_entry_diagnostics

from .conftest import make_entry, synth_month, url

LCM = "sensor.leicester_central_mosque"
MES = "sensor.masjid_e_salaam"


async def _setup(hass: HomeAssistant, ids: list[int]):
    entry = make_entry(ids)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} missing"
    return state.state


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, to: str) -> None:
    freezer.move_to(to)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_todays_times(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    await _setup(hass, [965, 2093])
    # Leicester Central Mosque, Sunday 8 Nov 2026 (GMT: local time == UTC)
    assert _state(hass, f"{LCM}_fajr_begins") == "2026-11-08T05:39:00+00:00"
    assert _state(hass, f"{LCM}_fajr_jamaat") == "2026-11-08T06:45:00+00:00"
    assert _state(hass, f"{LCM}_sunrise") == "2026-11-08T07:11:00+00:00"
    assert _state(hass, f"{LCM}_dhuhr_jamaat") == "2026-11-08T13:15:00+00:00"
    assert _state(hass, f"{LCM}_asr_begins") == "2026-11-08T14:35:00+00:00"
    assert _state(hass, f"{LCM}_maghrib_begins") == "2026-11-08T16:24:00+00:00"
    assert _state(hass, f"{LCM}_isha_jamaat") == "2026-11-08T18:30:00+00:00"
    assert _state(hass, f"{LCM}_jummah") == "2026-11-13T13:15:00+00:00"
    assert _state(hass, f"{LCM}_hijri_date") == "28 Jumada al-Awwal 1448"
    assert _state(hass, f"{LCM}_next_prayer") == "dhuhr"
    assert _state(hass, f"{LCM}_next_jamaat") == "2026-11-08T13:15:00+00:00"
    attrs = hass.states.get(f"{LCM}_isha_jamaat").attributes
    assert attrs["tomorrow"] == "2026-11-09T19:30:00+00:00"
    nxt = hass.states.get(f"{LCM}_next_prayer").attributes
    assert nxt["begins"] == "2026-11-08T11:51:00+00:00"
    assert nxt["jamaat"] == "2026-11-08T13:15:00+00:00"
    # Masjid-e-Salaam has its own device and times
    assert _state(hass, f"{MES}_dhuhr_jamaat") == "2026-11-08T12:45:00+00:00"


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_optional_sensors(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    await _setup(hass, [965, 2093])
    registry = er.async_get(hass)
    # 2093 holds two Jumu'ahs: a disabled "Jummah 2" exists for it, not for 965
    jummah_2 = registry.async_get(f"{MES}_jummah_2")
    assert jummah_2 is not None and jummah_2.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry.async_get(f"{LCM}_jummah_2") is None
    zawal = registry.async_get(f"{LCM}_zawal")
    assert zawal is not None and zawal.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry.async_get(f"{LCM}_asr_begins_2") is None


async def test_next_prayer_moves_on_at_jamaat(
    hass: HomeAssistant, mirror: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-08 12:00:00+00:00")
    await _setup(hass, [965])
    assert _state(hass, f"{LCM}_next_prayer") == "dhuhr"
    await _advance(hass, freezer, "2026-11-08 13:15:01+00:00")
    assert _state(hass, f"{LCM}_next_prayer") == "asr"
    assert _state(hass, f"{LCM}_next_jamaat") == "2026-11-08T15:15:00+00:00"
    await _advance(hass, freezer, "2026-11-08 18:30:01+00:00")
    assert _state(hass, f"{LCM}_next_prayer") == "fajr"
    assert _state(hass, f"{LCM}_next_jamaat") == "2026-11-09T06:45:00+00:00"


async def test_friday(
    hass: HomeAssistant, mirror: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-13 10:00:00+00:00")
    await _setup(hass, [2093])
    assert _state(hass, f"{MES}_next_prayer") == "jummah"
    assert _state(hass, f"{MES}_next_jamaat") == "2026-11-13T12:40:00+00:00"
    assert _state(hass, f"{MES}_jummah") == "2026-11-13T12:40:00+00:00"


async def test_midnight_rollover(
    hass: HomeAssistant, mirror: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-08 23:59:00+00:00")
    await _setup(hass, [965])
    assert _state(hass, f"{LCM}_fajr_begins") == "2026-11-08T05:39:00+00:00"
    assert _state(hass, f"{LCM}_hijri_date") == "28 Jumada al-Awwal 1448"
    await _advance(hass, freezer, "2026-11-09 00:00:02+00:00")
    assert _state(hass, f"{LCM}_fajr_begins") == "2026-11-09T05:41:00+00:00"
    assert _state(hass, f"{LCM}_hijri_date") == "29 Jumada al-Awwal 1448"


async def test_month_end_reads_next_month(
    hass: HomeAssistant, mirror: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-30 12:00:00+00:00")
    await _setup(hass, [965])
    attrs = hass.states.get(f"{LCM}_fajr_begins").attributes
    assert attrs["tomorrow"] == "2026-12-01T06:12:00+00:00"
    await _advance(hass, freezer, "2026-12-01 00:00:02+00:00")
    assert _state(hass, f"{LCM}_fajr_begins") == "2026-12-01T06:12:00+00:00"


@pytest.mark.parametrize(
    ("now", "months", "today_utc", "tomorrow_utc"),
    [
        # 24 -> 25 Oct 2026: BST ends. Fajr 05:39 local each day.
        ("2026-10-24 12:00:00+00:00", [(2026, 10), (2026, 11)],
         "2026-10-24T04:39:00+00:00", "2026-10-25T05:39:00+00:00"),
        # 27 -> 28 Mar 2027: BST starts.
        ("2027-03-27 12:00:00+00:00", [(2027, 3), (2027, 4)],
         "2027-03-27T05:39:00+00:00", "2027-03-28T04:39:00+00:00"),
    ],
)
async def test_clock_changes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory,
    now: str, months: list, today_utc: str, tomorrow_utc: str,
) -> None:
    freezer.move_to(now)
    for year, month in months:
        aioclient_mock.get(url(965, year, month), json=synth_month(965, year, month))
    await _setup(hass, [965])
    state = hass.states.get(f"{LCM}_fajr_begins")
    assert state.state == today_utc
    assert state.attributes["tomorrow"] == tomorrow_utc


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_maghrib_without_start_time(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    for month in (11, 12):
        aioclient_mock.get(url(965, 2026, month), json=synth_month(
            965, 2026, month, maghrib={"begins": [], "jamaah": ["16:24"]}))
    await _setup(hass, [965])
    assert _state(hass, f"{LCM}_maghrib_begins") == "2026-11-08T16:24:00+00:00"
    assert _state(hass, f"{LCM}_maghrib_jamaat") == "2026-11-08T16:24:00+00:00"


async def test_server_down_keeps_times(
    hass: HomeAssistant, mirror: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-08 12:00:00+00:00")
    entry = await _setup(hass, [965])
    await _advance(hass, freezer, "2026-11-08 12:00:20+00:00")   # let the saved copy flush

    mirror.clear_requests()
    for month in (11, 12):
        mirror.get(url(965, 2026, month), exc=aiohttp.ClientError("down"))

    # A scheduled refresh fails: sensors keep today's times
    await _advance(hass, freezer, "2026-11-08 15:01:00+00:00")
    assert _state(hass, f"{LCM}_isha_jamaat") == "2026-11-08T18:30:00+00:00"
    assert entry.runtime_data.update_interval == timedelta(minutes=30)

    # Home Assistant restarts while the server is still down: the saved copy is used
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, f"{LCM}_isha_jamaat") == "2026-11-08T18:30:00+00:00"

    # The server comes back: normal interval again
    mirror.clear_requests()
    for month in (11, 12):
        mirror.get(url(965, 2026, month), json=synth_month(965, 2026, month))
    await _advance(hass, freezer, "2026-11-08 15:40:00+00:00")
    assert entry.runtime_data.update_interval == timedelta(hours=3)


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_no_copy_and_server_down_retries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    for month in (11, 12):
        aioclient_mock.get(url(965, 2026, month), exc=aiohttp.ClientError("down"))
    entry = await _setup(hass, [965])
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_diagnostics(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    entry = await _setup(hass, [965, 2093])
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["options"] == {"masjids": [965, 2093]}
    assert diag["masjids"]["965"]["name"] == "Leicester Central Mosque"
    assert diag["masjids"]["965"]["days"] == 61
    assert diag["saved_months"] == ["2093/2026/11", "2093/2026/12", "965/2026/11", "965/2026/12"]
