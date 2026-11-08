"""Config and options flows."""

from __future__ import annotations

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr

from custom_components.masjid247.config_flow import parse_ids
from custom_components.masjid247.const import CONF_MASJIDS, DOMAIN

from .conftest import make_entry, url

pytestmark = pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("965", [965]), ("965, 2093", [965, 2093]), (" 965 ;2093\n3868 ", [965, 2093, 3868]),
     ("#965", [965]), ("965,965", [965]), ("", None), ("abc", None), ("965, x", None),
     ("0", None), ("12345678", None), ("-5", None)],
)
def test_parse_ids(text: str, expected) -> None:
    assert parse_ids(text) == expected


async def _start(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_add_two_masjids(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MASJIDS: "965, 2093"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Masjid 24/7"
    assert result["options"] == {CONF_MASJIDS: [965, 2093]}
    await hass.async_block_till_done()
    assert hass.states.get("sensor.leicester_central_mosque_fajr_jamaat") is not None
    assert hass.states.get("sensor.masjid_e_salaam_fajr_jamaat") is not None


async def test_invalid_ids(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MASJIDS: "Leicester"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MASJIDS: "invalid_ids"}


async def test_too_many(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MASJIDS: ", ".join(str(i) for i in range(1, 12))}
    )
    assert result["errors"] == {CONF_MASJIDS: "too_many"}


async def test_unknown_masjid(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    mirror.get(url(1234, 2026, 11), status=404, json={"error": "no timetable"})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MASJIDS: "965, 1234"}
    )
    assert result["errors"] == {CONF_MASJIDS: "not_found"}
    assert result["description_placeholders"]["ids"] == "1234"

    # Correcting it finishes the flow
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MASJIDS: "965"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("failure", [{"exc": aiohttp.ClientError()}, {"status": 500},
                                     {"status": 429}, {"text": "not json"}])
async def test_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, failure: dict
) -> None:
    aioclient_mock.get(url(965, 2026, 11), **failure)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MASJIDS: "965"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_only_one_entry(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    make_entry([965]).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_add_and_remove(hass: HomeAssistant, mirror: AiohttpClientMocker) -> None:
    entry = make_entry([965, 2093])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert {d.name for d in devices} == {"Leicester Central Mosque", "Masjid-e-Salaam"}

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema_default = next(iter(result["data_schema"].schema)).default()
    assert schema_default == "965, 2093"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MASJIDS: "965"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options == {CONF_MASJIDS: [965]}
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert {d.name for d in devices} == {"Leicester Central Mosque"}
    assert hass.states.get("sensor.leicester_central_mosque_fajr_jamaat").state != "unavailable"
