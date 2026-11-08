"""Masjid 24/7 prayer times for Home Assistant.

Reads each masjid's timetable from a mirror of the Masjid 24/7 API
(masjid247.mvppro.co.uk), so Home Assistant never loads Masjid 24/7's own servers.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import Masjid247Client
from .const import CONF_MASJIDS, DOMAIN, STORAGE_VERSION
from .coordinator import Masjid247ConfigEntry, Masjid247Coordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


def configured_ids(entry: Masjid247ConfigEntry) -> list[int]:
    """The masjid ids chosen in the config/options flow."""
    raw = entry.options.get(CONF_MASJIDS, entry.data.get(CONF_MASJIDS, []))
    return [int(x) for x in raw]


async def async_setup_entry(hass: HomeAssistant, entry: Masjid247ConfigEntry) -> bool:
    """Set up Masjid 24/7 from a config entry."""
    ids = configured_ids(entry)
    coordinator = Masjid247Coordinator(
        hass, entry, Masjid247Client(async_get_clientsession(hass)), ids
    )
    await coordinator.async_load_saved()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_stale_devices(hass, entry, ids)

    entry.async_on_unload(coordinator.async_add_listener(coordinator.async_schedule_tick))
    entry.async_on_unload(coordinator.async_cancel_tick)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_schedule_tick()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Masjid247ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: Masjid247ConfigEntry) -> None:
    """Delete the saved timetables when the integration is removed."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_options_updated(hass: HomeAssistant, entry: Masjid247ConfigEntry) -> None:
    """Masjids added or removed: reload to rebuild devices and sensors."""
    await hass.config_entries.async_reload(entry.entry_id)


def _remove_stale_devices(
    hass: HomeAssistant, entry: Masjid247ConfigEntry, ids: list[int]
) -> None:
    """Drop devices (and their sensors) for masjids taken out of the list."""
    registry = dr.async_get(hass)
    wanted = {str(i) for i in ids}
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        masjid = next((v for d, v in device.identifiers if d == DOMAIN), None)
        if masjid not in wanted:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
