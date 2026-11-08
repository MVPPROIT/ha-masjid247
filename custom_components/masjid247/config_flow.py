"""Config and options flows: the user types one or more Masjid IDs."""

from __future__ import annotations

import re
from typing import Any
from zoneinfo import ZoneInfo

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector
from homeassistant.util import dt as dt_util

from .api import CannotConnect, Masjid247Client, MasjidNotFound, ServerBusy, parse_month
from .const import CONF_MASJIDS, DEFAULT_TIMEZONE, DOMAIN, MAX_MASJIDS, SETUP_URL
from .coordinator import Masjid247ConfigEntry, months_from

_SPLIT = re.compile(r"[\s,;]+")


def parse_ids(text: str) -> list[int] | None:
    """ "965, 2093" -> [965, 2093]; None if anything is not a Masjid ID."""
    ids: list[int] = []
    for part in _SPLIT.split(text.strip()):
        if not part:
            continue
        part = part.lstrip("#")
        if not part.isdigit() or len(part) > 7 or int(part) == 0:
            return None
        if int(part) not in ids:
            ids.append(int(part))
    return ids or None


async def _validate(hass: HomeAssistant, ids: list[int]) -> list[int]:
    """Check each masjid has a timetable this month. Returns the ids that do not.

    The mirror fetches a masjid it has never seen on this first request, so this
    also warms it up. Raises CannotConnect if the server cannot be reached.
    """
    client = Masjid247Client(async_get_clientsession(hass))
    year, month = months_from(dt_util.utcnow().astimezone(ZoneInfo(DEFAULT_TIMEZONE)).date())[0]
    missing: list[int] = []
    for mid in ids:
        try:
            parse_month(await client.async_get_month(mid, year, month))
        except MasjidNotFound:
            missing.append(mid)
        except ServerBusy as err:
            raise CannotConnect(str(err)) from err
    return missing


async def _check(
    hass: HomeAssistant, user_input: dict[str, Any], errors: dict[str, str],
    placeholders: dict[str, str],
) -> list[int] | None:
    """Parse and verify the ids typed in. Fills `errors`; returns ids when all good."""
    ids = parse_ids(user_input.get(CONF_MASJIDS, ""))
    if ids is None:
        errors[CONF_MASJIDS] = "invalid_ids"
        return None
    if len(ids) > MAX_MASJIDS:
        errors[CONF_MASJIDS] = "too_many"
        return None
    try:
        missing = await _validate(hass, ids)
    except CannotConnect:
        errors["base"] = "cannot_connect"
        return None
    if missing:
        errors[CONF_MASJIDS] = "not_found"
        placeholders["ids"] = ", ".join(str(m) for m in missing)
        return None
    return ids


def _schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_MASJIDS, default=default): TextSelector()})


class Masjid247ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add Masjid 24/7."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Masjid ID(s)."""
        errors: dict[str, str] = {}
        placeholders = {"setup_url": SETUP_URL, "ids": ""}
        if user_input is not None:
            ids = await _check(self.hass, user_input, errors, placeholders)
            if ids is not None:
                return self.async_create_entry(
                    title="Masjid 24/7", data={}, options={CONF_MASJIDS: ids}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_schema((user_input or {}).get(CONF_MASJIDS, "")),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Masjid247ConfigEntry) -> OptionsFlow:
        """Change which masjids are shown."""
        return Masjid247OptionsFlow()


class Masjid247OptionsFlow(OptionsFlow):
    """Add or remove masjids."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the Masjid ID list."""
        errors: dict[str, str] = {}
        placeholders = {"setup_url": SETUP_URL, "ids": ""}
        if user_input is not None:
            ids = await _check(self.hass, user_input, errors, placeholders)
            if ids is not None:
                return self.async_create_entry(data={CONF_MASJIDS: ids})
            default = user_input.get(CONF_MASJIDS, "")
        else:
            current = self.config_entry.options.get(CONF_MASJIDS, [])
            default = ", ".join(str(i) for i in current)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(default),
            errors=errors,
            description_placeholders=placeholders,
        )
