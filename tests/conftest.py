"""Shared fixtures: real mirror files for masjids 965 and 2093 (Nov + Dec 2026)."""

from __future__ import annotations

import calendar
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.masjid247.const import CACHE_BASE_URL, CONF_MASJIDS, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict[str, Any]:
    """A fixture file as JSON."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def url(mid: int, year: int, month: int) -> str:
    """Mirror URL of one masjid-month."""
    return f"{CACHE_BASE_URL}/{mid}/{year}/{month}.json"


def synth_month(mid: int, year: int, month: int, **changes: Any) -> dict[str, Any]:
    """A whole month where every day repeats 965's 8 Nov 2026, with `changes` applied
    to each day (e.g. maghrib={"begins": [], "jamaah": ["16:24"]})."""
    base = load("965-2026-11.json")
    template = next(d for d in base["days"] if d["date"] == "2026-11-08")
    days = []
    for n in range(1, calendar.monthrange(year, month)[1] + 1):
        day = copy.deepcopy(template)
        day["date"] = f"{year}-{month:02d}-{n:02d}"
        day.update(copy.deepcopy(changes))
        days.append(day)
    return {**base, "mosqueId": mid, "year": year, "month": month, "days": days}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/masjid247."""
    return


@pytest.fixture
def mirror(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """The mirror serving the real Nov/Dec 2026 files for 965 and 2093."""
    for mid in (965, 2093):
        for month in (11, 12):
            aioclient_mock.get(url(mid, 2026, month), json=load(f"{mid}-2026-{month}.json"))
    return aioclient_mock


def make_entry(ids: list[int]) -> MockConfigEntry:
    """A config entry for the given masjids."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Masjid 24/7",
        data={},
        options={CONF_MASJIDS: ids},
        entry_id="masjid247_test",
    )
