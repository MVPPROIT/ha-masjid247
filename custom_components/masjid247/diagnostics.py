"""Diagnostics: what the integration holds (no secrets exist to redact)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CACHE_BASE_URL
from .coordinator import Masjid247ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Masjid247ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "server": CACHE_BASE_URL,
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "update_interval": str(coordinator.update_interval),
        "saved_months": coordinator.saved_months,
        "missing": sorted(coordinator.missing),
        "masjids": {
            str(mid): {
                "name": md.name,
                "timezone": str(md.tz),
                "days": len(md.days),
                "first_day": min(md.days).isoformat(),
                "last_day": max(md.days).isoformat(),
            }
            for mid, md in (coordinator.data or {}).items()
        },
    }
