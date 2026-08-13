"""Integration test for the ``rebuild_period_report`` service.

We do not exercise the real Recorder here (setting it up in
``pytest-homeassistant-custom-component`` is expensive). Instead we mock
``homeassistant.components.recorder.history.get_significant_states`` to
return synthetic State objects and verify the produced report shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data

KYIV = ZoneInfo("Europe/Kyiv")


def _fake_states_for_entity(entity_id: str, currency: str = "EUR") -> list[State]:
    """Return synthetic cumulative-cost anchors at each KYIV hour boundary."""
    boundaries = [datetime(2026, 6, 1, hour, tzinfo=KYIV) for hour in range(5)]
    values = ["0.00", "1.00", "2.50", "4.00", "5.75"]
    return [
        State(
            entity_id,
            value,
            {"unit_of_measurement": currency},
            last_updated=boundary.astimezone(UTC),
        )
        for value, boundary in zip(values, boundaries, strict=True)
    ]


@pytest.mark.asyncio
async def test_rebuild_period_report_end_to_end(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    def _fake_get(*args, **kwargs):  # type: ignore[no-untyped-def]
        entity_ids = kwargs.get("entity_ids") or []
        return {eid: _fake_states_for_entity(eid) for eid in entity_ids}

    with patch(
        "custom_components.shared_energy_ledger.report_builder.history.get_significant_states",
        side_effect=_fake_get,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            "rebuild_period_report",
            {
                "start": datetime(2026, 6, 1, tzinfo=KYIV).isoformat(),
                "end": datetime(2026, 6, 1, 4, tzinfo=KYIV).isoformat(),
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["schema_version"] == 2
    assert response["currency"] == "EUR"
    assert set(response["tenants"].keys()) == {"flat-1", "flat-2"}
    for tenant in response["tenants"].values():
        assert tenant["coverage_seconds"] > 0
        # cumulative jump: 0 -> 5.75 over 4 hours; hourly deltas sum to 5.75
        assert tenant["known_cost"] in {"5.75", "0.00"}
    # revision hash present, matches the canonical body
    assert isinstance(response["revision"], str) and len(response["revision"]) == 64
    assert response.get("transition_excluded_seconds") == 0
    assert "period" in response and "start_local" in response["period"]

    # Filtering by unknown tenant slug must fail closed.
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
                "start": datetime(2026, 6, 1, tzinfo=KYIV).isoformat(),
                "end": datetime(2026, 6, 1, 4, tzinfo=KYIV).isoformat(),
                "tenant": "ghost",
            },
            blocking=True,
            return_response=True,
        )


@pytest.mark.asyncio
async def test_rebuild_period_report_scoped_to_single_tenant(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    def _fake_get(*args, **kwargs):  # type: ignore[no-untyped-def]
        entity_ids = kwargs.get("entity_ids") or []
        return {eid: _fake_states_for_entity(eid) for eid in entity_ids}

    with patch(
        "custom_components.shared_energy_ledger.report_builder.history.get_significant_states",
        side_effect=_fake_get,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            "rebuild_period_report",
            {
                "start": datetime(2026, 6, 1, tzinfo=KYIV).isoformat(),
                "end": datetime(2026, 6, 1, 4, tzinfo=KYIV).isoformat(),
                "tenant": "flat-1",
            },
            blocking=True,
            return_response=True,
        )
    assert response is not None
    assert set(response["tenants"].keys()) == {"flat-1"}
