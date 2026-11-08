"""Prayer-time sensors: one device per masjid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import times
from .const import DOMAIN, PRAYERS, SETUP_URL
from .coordinator import Masjid247ConfigEntry, Masjid247Coordinator
from .times import MasjidData

PARALLEL_UPDATES = 0

MAX_JUMMAH = 5


@dataclass(frozen=True, kw_only=True)
class Masjid247SensorDescription(SensorEntityDescription):
    """A sensor whose value is computed for a given day of a masjid's timetable."""

    value_fn: Callable[[MasjidData, date], datetime | str | None]
    with_tomorrow: bool = True


def _time(key: str, fn: Callable[[MasjidData, date], datetime | None], *,
          enabled: bool = True, translation_key: str | None = None) -> Masjid247SensorDescription:
    return Masjid247SensorDescription(
        key=key,
        translation_key=translation_key or key,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=enabled,
        value_fn=fn,
    )


def _begins(prayer: str, index: int = 0):
    return lambda md, day: times.begins(md, day, prayer, index)


def _jamaat(prayer: str, index: int = 0):
    return lambda md, day: times.jamaat(md, day, prayer, index)


def _field(name: str):
    return lambda md, day: times.day_field(md, day, name)


def _jummah(index: int):
    return lambda md, day: times.jummah(md, day, index)


# Always created, in the order they appear on the device page.
CORE: tuple[Masjid247SensorDescription, ...] = (
    _time("fajr_beginning", _begins("fajr")),
    _time("fajr_jamaat", _jamaat("fajr")),
    _time("sunrise", _field("sunrise")),
    _time("dhuhr_beginning", _begins("dhuhr")),
    _time("dhuhr_jamaat", _jamaat("dhuhr")),
    _time("asr_beginning", _begins("asr")),
    _time("asr_jamaat", _jamaat("asr")),
    _time("maghrib_beginning", _begins("maghrib")),
    _time("maghrib_jamaat", _jamaat("maghrib")),
    _time("isha_beginning", _begins("isha")),
    _time("isha_jamaat", _jamaat("isha")),
    _time("jummah", _jummah(0)),
    Masjid247SensorDescription(
        key="hijri_date", translation_key="hijri_date", value_fn=times.hijri,
        with_tomorrow=True,
    ),
    # Sehri end is only filled in during Ramadan; zawal by some masjids. Off by default.
    _time("sehri_end", _field("sehri_end"), enabled=False),
    _time("zawal", _field("zawal"), enabled=False),
)


def extra_descriptions(md: MasjidData) -> list[Masjid247SensorDescription]:
    """Sensors for values only some masjids publish (2nd Asr start, 2nd jamaats,
    more than one Jumu'ah). Created only when this masjid's timetable has them;
    disabled by default."""
    out: list[Masjid247SensorDescription] = []
    days = list(md.days.values())
    if any(len(d.begins["asr"]) > 1 for d in days):
        out.append(_time("asr_beginning_2", _begins("asr", 1), enabled=False))
    for prayer in PRAYERS:
        if any(len(d.jamaat[prayer]) > 1 for d in days):
            out.append(_time(f"{prayer}_jamaat_2", _jamaat(prayer, 1), enabled=False))
    most = min(MAX_JUMMAH, max((len(d.jummah) for d in days), default=0))
    for n in range(2, most + 1):
        out.append(_time(f"jummah_{n}", _jummah(n - 1), enabled=False,
                         translation_key="jummah_n"))
    return out


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Masjid247ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensors for every masjid with a timetable, and for any that appear later."""
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[SensorEntity] = []
        for mid, md in (coordinator.data or {}).items():
            descriptions = [*CORE, *extra_descriptions(md)]
            for description in descriptions:
                uid = f"{mid}_{description.key}"
                if uid in added:
                    continue
                added.add(uid)
                new.append(Masjid247Sensor(coordinator, md, description))
            for cls in (NextPrayerSensor, NextJamaatSensor):
                uid = f"{mid}_{cls.KEY}"
                if uid not in added:
                    added.add(uid)
                    new.append(cls(coordinator, md))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class _MasjidEntity(CoordinatorEntity[Masjid247Coordinator], SensorEntity):
    """Common bits: device, availability, the masjid's data."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Masjid247Coordinator, md: MasjidData, key: str) -> None:
        super().__init__(coordinator)
        self._masjid_id = md.masjid_id
        self._attr_unique_id = f"{md.masjid_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(md.masjid_id))},
            name=md.name,
            manufacturer="Masjid 24/7",
            model=f"Masjid {md.masjid_id}",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=SETUP_URL,
        )

    @property
    def masjid(self) -> MasjidData | None:
        """This masjid's current data."""
        return (self.coordinator.data or {}).get(self._masjid_id)

    @property
    def available(self) -> bool:
        """Available while there is a timetable for this masjid."""
        return self.masjid is not None

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        """UTC ISO string, the same form Home Assistant uses for timestamp states."""
        return dt_util.as_utc(value).isoformat() if value is not None else None


class Masjid247Sensor(_MasjidEntity):
    """Today's value of one time (or the Hijri date); tomorrow's as an attribute."""

    entity_description: Masjid247SensorDescription

    def __init__(
        self,
        coordinator: Masjid247Coordinator,
        md: MasjidData,
        description: Masjid247SensorDescription,
    ) -> None:
        super().__init__(coordinator, md, description.key)
        self.entity_description = description
        if description.translation_key == "jummah_n":
            self._attr_translation_placeholders = {"number": description.key.rsplit("_", 1)[1]}

    def _today(self, md: MasjidData) -> date:
        return md.local_date(dt_util.utcnow())

    @property
    def native_value(self) -> datetime | str | None:
        """Value for the masjid's current local date."""
        md = self.masjid
        if md is None:
            return None
        return self.entity_description.value_fn(md, self._today(md))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Tomorrow's value, so automations and cards can look ahead."""
        md = self.masjid
        if md is None or not self.entity_description.with_tomorrow:
            return None
        value = self.entity_description.value_fn(md, self._today(md) + timedelta(days=1))
        return {"tomorrow": self._iso(value) if isinstance(value, datetime) else value}


class NextPrayerSensor(_MasjidEntity):
    """Which prayer's jamaat is next ("jummah" on Fridays)."""

    KEY = "next_prayer"
    _attr_translation_key = KEY
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["fajr", "dhuhr", "jummah", "asr", "maghrib", "isha"]

    def __init__(self, coordinator: Masjid247Coordinator, md: MasjidData) -> None:
        super().__init__(coordinator, md, self.KEY)

    def _event(self) -> times.PrayerEvent | None:
        md = self.masjid
        return times.next_prayer(md, dt_util.utcnow()) if md else None

    @property
    def native_value(self) -> str | None:
        """The prayer key."""
        event = self._event()
        return event.prayer if event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Its Beginning and Jam’aat times."""
        event = self._event()
        if event is None:
            return None
        return {"beginning": self._iso(event.begins), "jamaat": self._iso(event.jamaat)}


class NextJamaatSensor(_MasjidEntity):
    """When the next jamaat is: a timestamp to trigger automations from."""

    KEY = "next_jamaat"
    _attr_translation_key = KEY
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: Masjid247Coordinator, md: MasjidData) -> None:
        super().__init__(coordinator, md, self.KEY)

    def _event(self) -> times.PrayerEvent | None:
        md = self.masjid
        return times.next_prayer(md, dt_util.utcnow()) if md else None

    @property
    def native_value(self) -> datetime | None:
        """Jamaat time (or the start, where the masjid gives no jamaat)."""
        event = self._event()
        return event.when if event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Which prayer it is."""
        event = self._event()
        return {"prayer": event.prayer} if event else None
