"""Integration test for the ``rebuild_period_report`` service.

The report is recomputed from meter and price history via the interval engine.
We mock ``history.get_significant_states`` to return synthetic kWh and price
states and assert the produced report reconciles to a hand-computed answer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data

KYIV = ZoneInfo("Europe/Kyiv")

# Five hourly boundaries 00:00..04:00 local.
_BOUNDARIES = [datetime(2026, 6, 1, hour, tzinfo=KYIV) for hour in range(5)]


def _cumulative(entity_id: str, values: list[str], unit: str) -> list[State]:
    return [
        State(entity_id, value, {"unit_of_measurement": unit}, last_updated=b.astimezone(UTC))
        for value, b in zip(values, _BOUNDARIES, strict=True)
    ]


def _series(entity_id: str) -> list[State]:
    data = _happy_entry_data()
    grid_import = data["grid"]["import_energy_entity"]
    grid_price = data["grid"]["import_price_entity"]
    flat1 = data["tenants"][0]["energy_entity"]
    flat2 = data["tenants"][1]["energy_entity"]
    if entity_id == grid_import:
        return _cumulative(entity_id, ["0", "2", "4", "6", "8"], "kWh")
    if entity_id in (flat1, flat2):
        return _cumulative(entity_id, ["0", "1", "2", "3", "4"], "kWh")
    if entity_id == grid_price:
        # Constant 0.30 EUR/kWh, one anchor before the period, persisting.
        early = (_BOUNDARIES[0] - timedelta(hours=1)).astimezone(UTC)
        return [State(entity_id, "0.30", {"unit_of_measurement": "EUR/kWh"}, last_updated=early)]
    return []


def _fake_get(*args, **kwargs):  # type: ignore[no-untyped-def]
    entity_ids = kwargs.get("entity_ids") or []
    return {eid: _series(eid) for eid in entity_ids}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_report_reconciles_to_hand_computed_cost(hass: HomeAssistant) -> None:
    await _setup(hass)
    with patch(
        "custom_components.shared_energy_ledger.report_builder.history.get_significant_states",
        side_effect=_fake_get,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            "rebuild_period_report",
            {
                "start": _BOUNDARIES[0].isoformat(),
                "end": _BOUNDARIES[4].isoformat(),
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["schema_version"] == 3
    assert response["currency"] == "EUR"
    assert set(response["tenants"].keys()) == {"flat-1", "flat-2"}
    # Each flat consumes 1 kWh/hour for 4 hours at 0.30 EUR/kWh = 1.20, all grid.
    for tenant in response["tenants"].values():
        assert tenant["known_cost"] == "1.20"
        assert tenant["grid_cost"] == "1.20"
        assert tenant["pv_cost"] == "0.00"
    # Grid import delta (2/h) exactly serves consumption: reconciliation ~ 0.
    assert response["reconciliation_kwh"] == "0.000000"
    assert response["unavailable_seconds"] == 0
    assert isinstance(response["revision"], str) and len(response["revision"]) == 64


@pytest.mark.asyncio
async def test_report_scoped_to_single_tenant(hass: HomeAssistant) -> None:
    await _setup(hass)
    with patch(
        "custom_components.shared_energy_ledger.report_builder.history.get_significant_states",
        side_effect=_fake_get,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            "rebuild_period_report",
            {
                "start": _BOUNDARIES[0].isoformat(),
                "end": _BOUNDARIES[4].isoformat(),
                "tenant": "flat-1",
            },
            blocking=True,
            return_response=True,
        )
    assert response is not None
    assert set(response["tenants"].keys()) == {"flat-1"}
    assert response["tenants"]["flat-1"]["known_cost"] == "1.20"


@pytest.mark.asyncio
async def test_unknown_tenant_fails_closed(hass: HomeAssistant) -> None:
    await _setup(hass)
    with (
        patch(
            "custom_components.shared_energy_ledger.report_builder.history.get_significant_states",
            side_effect=_fake_get,
        ),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "rebuild_period_report",
            {
                "start": _BOUNDARIES[0].isoformat(),
                "end": _BOUNDARIES[4].isoformat(),
                "tenant": "ghost",
            },
            blocking=True,
            return_response=True,
        )
