"""Fetch each masjid's timetable, keep the last good copy, and tick at the right moments."""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CannotConnect,
    DayTimes,
    Masjid247Client,
    MasjidNotFound,
    ServerBusy,
    parse_month,
)
from .const import (
    DEFAULT_TIMEZONE,
    DOMAIN,
    RETRY_INTERVAL,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .times import MasjidData, next_prayer

_LOGGER = logging.getLogger(__name__)

type Masjid247ConfigEntry = ConfigEntry[Masjid247Coordinator]


def months_from(day: date) -> list[tuple[int, int]]:
    """The month of `day` and the one after it."""
    nxt = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return [(day.year, day.month), nxt]


class Masjid247Coordinator(DataUpdateCoordinator[dict[int, MasjidData]]):
    """Holds every configured masjid's timetable (current + next month).

    Timetables are monthly and change rarely, so the last good copy is kept on disk:
    if the server is down, even across a Home Assistant restart, sensors keep showing
    the right times for as long as the saved months last.
    """

    config_entry: Masjid247ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Masjid247ConfigEntry,
        client: Masjid247Client,
        masjid_ids: list[int],
    ) -> None:
        """Set up the coordinator for the configured masjid ids."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.masjid_ids = masjid_ids
        self.missing: set[int] = set()
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._raw: dict[str, dict[str, Any]] = {}       # "id/year/month" -> mirror file
        self._unsub_tick: CALLBACK_TYPE | None = None
        self._offline_logged = False

    # -- saved copy -----------------------------------------------------------------
    async def async_load_saved(self) -> None:
        """Load the timetables saved by a previous run."""
        saved = await self._store.async_load()
        months = saved.get("months") if isinstance(saved, dict) else None
        if isinstance(months, dict):
            self._raw = {k: v for k, v in months.items() if isinstance(v, dict)}

    @property
    def saved_months(self) -> list[str]:
        """Keys of the months currently held, for diagnostics."""
        return sorted(self._raw)

    def _tz_for(self, masjid_id: int) -> ZoneInfo:
        for key, raw in self._raw.items():
            if key.startswith(f"{masjid_id}/"):
                try:
                    return ZoneInfo(parse_month(raw).timezone)
                except ValueError:
                    continue
        return ZoneInfo(DEFAULT_TIMEZONE)

    def _prune(self) -> None:
        """Forget months before the current one, and masjids no longer configured."""
        keep: dict[str, dict[str, Any]] = {}
        for key, raw in self._raw.items():
            try:
                mid, year, month = (int(p) for p in key.split("/"))
            except ValueError:
                continue
            if mid not in self.masjid_ids:
                continue
            current = months_from(dt_util.utcnow().astimezone(self._tz_for(mid)).date())[0]
            if (year, month) >= current:
                keep[key] = raw
        self._raw = keep

    def _build(self) -> dict[int, MasjidData]:
        data: dict[int, MasjidData] = {}
        for mid in self.masjid_ids:
            months = sorted(
                (k for k in self._raw if k.startswith(f"{mid}/")),
                key=lambda k: tuple(int(p) for p in k.split("/")[1:]),
            )
            days: dict[date, DayTimes] = {}
            name, tz = f"Masjid {mid}", DEFAULT_TIMEZONE
            for key in months:
                try:
                    month = parse_month(self._raw[key])
                except ValueError:
                    continue
                days.update(month.days)
                name, tz = month.name, month.timezone
            if days:
                data[mid] = MasjidData(mid, name, ZoneInfo(tz), days)
        return data

    # -- refresh --------------------------------------------------------------------
    async def _async_update_data(self) -> dict[int, MasjidData]:
        attempts = failures = 0
        last_error: Exception | None = None
        not_found: set[int] = set()

        for mid in self.masjid_ids:
            today = dt_util.utcnow().astimezone(self._tz_for(mid)).date()
            for index, (year, month) in enumerate(months_from(today)):
                attempts += 1
                try:
                    self._raw[f"{mid}/{year}/{month}"] = await self.client.async_get_month(
                        mid, year, month
                    )
                except MasjidNotFound:
                    if index == 0:          # next month unpublished is normal
                        not_found.add(mid)
                except (CannotConnect, ServerBusy) as err:
                    failures += 1
                    last_error = err

        self._prune()
        data = self._build()

        if failures:
            self.update_interval = RETRY_INTERVAL
            if not data:
                raise UpdateFailed(
                    f"Could not reach the Masjid 24/7 prayer-time server: {last_error}"
                )
            if not self._offline_logged:
                _LOGGER.warning(
                    "Masjid 24/7 prayer-time server unreachable (%s); "
                    "showing saved timetables until it is back",
                    last_error,
                )
                self._offline_logged = True
        else:
            self.update_interval = UPDATE_INTERVAL
            if self._offline_logged:
                _LOGGER.info("Masjid 24/7 prayer-time server reachable again")
            self._offline_logged = False

        missing = {mid for mid in self.masjid_ids if mid not in data}
        if missing != self.missing and missing:
            _LOGGER.warning(
                "No prayer timetable for masjid %s on Masjid 24/7; check the Masjid ID",
                ", ".join(str(m) for m in sorted(missing)),
            )
        self.missing = missing
        if not_found - missing:
            _LOGGER.debug("Masjid(s) %s: current month gone, using saved copy", not_found)

        if attempts > failures:
            self._store.async_delay_save(lambda: {"months": self._raw}, 10)
        return data

    # -- ticks: midnight rollover and "next prayer" changes ---------------------------
    @callback
    def async_schedule_tick(self) -> None:
        """Wake at the next moment any sensor's value changes without new data.

        That is the earliest of each masjid's next local midnight and next jamaat.
        Registered as a coordinator listener, so it re-arms after every update.
        """
        self.async_cancel_tick()
        if not self.data:
            return
        now = dt_util.utcnow()
        moments: list[datetime] = []
        for md in self.data.values():
            moments.append(md.next_midnight(now))
            event = next_prayer(md, now)
            if event is not None:
                moments.append(event.when)
        if moments:
            self._unsub_tick = async_track_point_in_utc_time(
                self.hass, self._tick, dt_util.as_utc(min(moments))
            )

    @callback
    def async_cancel_tick(self) -> None:
        """Stop the pending tick."""
        if self._unsub_tick is not None:
            self._unsub_tick()
            self._unsub_tick = None

    @callback
    def _tick(self, _now: datetime) -> None:
        self._unsub_tick = None
        self.async_update_listeners()       # sensors recompute; schedule listener re-arms
