"""Vertical path: real config flow -> unchanged entry -> report reconcile.

Builds an entry through the public config flow, feeds synthetic meter and
price history, rebuilds the period report, and compares every tenant total to
an independently hand-calculated answer. Maps to plan section 6 and
requirement I7.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType

from custom_components.shared_energy_ledger.const import (
    CONF_CURRENCY,
    CONF_IMPORT_ENERGY,
    CONF_IMPORT_PRICE,
    DOMAIN,
)

KYIV = ZoneInfo("Europe/Kyiv")
_BOUNDARIES = [datetime(2026, 6, 1, hour, tzinfo=KYIV) for hour in range(5)]


def _cumulative(entity_id: str, values: list[str], unit: str) -> list[State]:
    return [
        State(entity_id, value, {"unit_of_measurement": unit}, last_updated=b.astimezone(UTC))
        for value, b in zip(values, _BOUNDARIES, strict=True)
    ]


@pytest.mark.asyncio
async def test_config_flow_to_report_hand_calculated(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    step = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CURRENCY: "EUR",
            CONF_IMPORT_ENERGY: "sensor.grid_import",
            CONF_IMPORT_PRICE: "sensor.grid_price",
        },
    )
    assert step["step_id"] == "optional"
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"include_pv": False, "include_battery": False, "include_whole_building": False},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "slug": "flat-1",
            "name": "Flat 1",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.flat_1_e",
            "add_another": True,
        },
    )
    final = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "slug": "flat-2",
            "name": "Flat 2",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.flat_2_e",
            "add_another": False,
        },
    )
    assert final["type"] == FlowResultType.CREATE_ENTRY
    entry_data: dict[str, Any] = final["data"]
    await hass.async_block_till_done()

    def _series(entity_id: str) -> list[State]:
        if entity_id == "sensor.grid_import":
            return _cumulative(entity_id, ["0", "2", "4", "6", "8"], "kWh")
        if entity_id in ("sensor.flat_1_e", "sensor.flat_2_e"):
            return _cumulative(entity_id, ["0", "1", "2", "3", "4"], "kWh")
        if entity_id == "sensor.grid_price":
            early = (_BOUNDARIES[0] - timedelta(hours=1)).astimezone(UTC)
            return [
                State(
                    entity_id,
                    "0.30",
                    {"unit_of_measurement": "EUR/kWh"},
                    last_updated=early,
                )
            ]
        return []

    with patch(
        "custom_components.shared_energy_ledger.report_builder.history.get_significant_states",
        side_effect=lambda *args, **kwargs: {
            eid: _series(eid) for eid in (kwargs.get("entity_ids") or [])
        },
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
    assert response["currency"] == entry_data[CONF_CURRENCY]
    # 1 kWh/hour * 4 hours * 0.30 EUR/kWh = 1.20 per tenant, all grid.
    for slug in ("flat-1", "flat-2"):
        tenant = response["tenants"][slug]
        assert tenant["known_cost"] == "1.20"
        assert tenant["grid_cost"] == "1.20"
        assert tenant["grid_kwh"] == "4.000000"
        assert tenant["pv_kwh"] == "0.000000"
        assert tenant["battery_kwh"] == "0.000000"
        assert tenant["pv_cost"] == "0.00"
        assert tenant["battery_cost"] == "0.00"
    assert response["reconciliation_kwh"] == "0.000000"
    assert response["unavailable_seconds"] == 0
