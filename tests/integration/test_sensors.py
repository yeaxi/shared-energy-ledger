"""Tests for sensor and binary_sensor behavior against a live coordinator."""

from __future__ import annotations

import pytest
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN

from .test_setup import _happy_entry_data


@pytest.mark.asyncio
async def test_freshness_gate_off_when_no_upstream_i1(hass: HomeAssistant) -> None:
    """I1 + I2: with no upstream states, the grid freshness binary sensor is off."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.shared_energy_ledger_grid_data_fresh")
    assert state is not None
    assert state.state == STATE_OFF


@pytest.mark.asyncio
async def test_tenant_share_is_unavailable_without_upstream_i1(
    hass: HomeAssistant,
) -> None:
    """I1: per-tenant share stays unavailable, not 0, without upstream meters."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for entity_id in (
        "sensor.shared_energy_ledger_tenant_flat_1_share",
        "sensor.shared_energy_ledger_tenant_flat_2_share",
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_tenant_slug_prefixes_entity_ids_and_device_names(
    hass: HomeAssistant,
) -> None:
    """Tenant slug is the entity-id prefix; display name is the device name."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    share = entity_registry.async_get("sensor.shared_energy_ledger_tenant_flat_1_share")
    assert share is not None
    assert share.unique_id.endswith(":id-a:tenant_share")
    assert share.has_entity_name is True

    fresh = hass.states.get("binary_sensor.shared_energy_ledger_tenant_flat_1_data_fresh")
    assert fresh is not None

    device = device_registry.async_get(share.device_id) if share.device_id else None
    assert device is not None
    assert device.name == "Flat 1"

    hub = entity_registry.async_get("sensor.shared_energy_ledger_grid_import_price")
    assert hub is not None
    hub_device = device_registry.async_get(hub.device_id) if hub.device_id else None
    assert hub_device is not None
    assert hub_device.name == entry.title
    assert device.via_device_id == hub_device.id
