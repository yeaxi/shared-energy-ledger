"""I4: residual allocation fails closed when residual input timestamps skew."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN
from custom_components.shared_energy_ledger.models import AllocationPolicy


def _residual_entry_data(skew_s: int = 180) -> dict[str, Any]:
    return {
        "currency": "EUR",
        "grid": {
            "import_energy_entity": "sensor.demo_grid_import",
            "import_price_entity": "sensor.demo_grid_price",
        },
        "whole_building": {"energy_entity": "sensor.demo_wb_energy"},
        "freshness": {"alignment_skew_s": skew_s},
        "tenants": [
            {
                "tenant_id": "id-a",
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": AllocationPolicy.DIRECT_METER.value,
                "energy_entity": "sensor.demo_flat_1_energy",
            },
            {
                "tenant_id": "id-b",
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": AllocationPolicy.RESIDUAL_OF_TOTAL_MINUS_OTHERS.value,
            },
        ],
    }


def _set(hass: HomeAssistant, entity_id: str, state: str, unit: str) -> None:
    hass.states.async_set(entity_id, state, {"unit_of_measurement": unit})


async def _boot(hass: HomeAssistant, skew_s: int = 180) -> Any:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_residual_entry_data(skew_s), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _set_common_meters(hass: HomeAssistant) -> None:
    _set(hass, "sensor.demo_grid_import", "1000", "kWh")
    _set(hass, "sensor.demo_grid_price", "0.30", "EUR/kWh")
    _set(hass, "sensor.demo_flat_1_energy", "40", "kWh")
    _set(hass, "sensor.demo_wb_energy", "100", "kWh")


@pytest.mark.asyncio
async def test_residual_unavailable_when_inputs_skew_beyond_window(
    hass: HomeAssistant,
) -> None:
    skew_s = 180
    entry = await _boot(hass, skew_s=skew_s)
    coordinator = entry.runtime_data
    base = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)

    with freeze_time(base) as frozen:
        _set(hass, "sensor.demo_wb_energy", "100", "kWh")
        frozen.move_to(base + timedelta(seconds=skew_s + 1))
        _set(hass, "sensor.demo_grid_import", "1000", "kWh")
        _set(hass, "sensor.demo_grid_price", "0.30", "EUR/kWh")
        _set(hass, "sensor.demo_flat_1_energy", "40", "kWh")
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    residual = coordinator.data.allocations["flat-2"]
    direct = coordinator.data.allocations["flat-1"]
    assert residual.accounting_energy is None
    assert residual.provenance == "unavailable"
    assert direct.accounting_energy is not None
    assert direct.provenance == "direct_meter"


@pytest.mark.asyncio
async def test_residual_available_when_inputs_aligned_at_skew_bound(
    hass: HomeAssistant,
) -> None:
    skew_s = 180
    entry = await _boot(hass, skew_s=skew_s)
    coordinator = entry.runtime_data
    base = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)

    with freeze_time(base) as frozen:
        _set_common_meters(hass)
        frozen.move_to(base + timedelta(seconds=skew_s))
        # Refresh timestamps of residual inputs together at the skew bound.
        _set(hass, "sensor.demo_wb_energy", "100", "kWh")
        _set(hass, "sensor.demo_flat_1_energy", "40", "kWh")
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    residual = coordinator.data.allocations["flat-2"]
    direct = coordinator.data.allocations["flat-1"]
    assert residual.accounting_energy is not None
    assert residual.provenance == "residual_of_total_minus_others"
    assert direct.accounting_energy is not None
    assert direct.provenance == "direct_meter"
