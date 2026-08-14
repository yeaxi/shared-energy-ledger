"""Tests for Lovelace dashboard provisioning after config-entry setup."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.shared_energy_ledger.const import CONFIG_ENTRY_VERSION, DOMAIN
from custom_components.shared_energy_ledger.dashboard import (
    DASHBOARD_URL_PATH,
    MANAGED_FLAG,
    build_dashboard_config,
    should_overwrite,
)

from .test_battery_ledger_flow import _entry_with_battery
from .test_setup import _happy_entry_data


def test_build_dashboard_config_includes_tenant_views() -> None:
    """Overview plus one view per tenant, in display order."""
    config = build_dashboard_config(
        title="Shared Energy Ledger (EUR)",
        freshness_ids=["binary_sensor.shared_energy_ledger_grid_data_fresh"],
        price_ids=["sensor.shared_energy_ledger_grid_import_price"],
        battery_ids=["sensor.shared_energy_ledger_battery_weighted_cost"],
        tenants=(
            (
                "flat-1",
                "Flat 1",
                ["sensor.shared_energy_ledger_tenant_flat_1_share"],
            ),
            (
                "flat-2",
                "Flat 2",
                ["sensor.shared_energy_ledger_tenant_flat_2_share"],
            ),
        ),
    )
    assert config[MANAGED_FLAG] is True
    paths = [view["path"] for view in config["views"]]
    assert paths == ["overview", "flat-1", "flat-2"]
    tenant_view = config["views"][1]
    assert tenant_view["title"] == "Flat 1"
    assert (
        "sensor.shared_energy_ledger_tenant_flat_1_share"
        in tenant_view["cards"][0]["entities"]
    )


def test_build_dashboard_config_omits_empty_sections() -> None:
    config = build_dashboard_config(
        title="Ledger",
        freshness_ids=[],
        price_ids=[],
        battery_ids=[],
        tenants=(("flat-1", "Flat 1", []),),
    )
    overview = config["views"][0]
    assert overview["path"] == "overview"
    assert all(card["type"] == "markdown" for card in overview["cards"])
    assert [view["path"] for view in config["views"]] == ["overview"]


def test_should_overwrite_only_managed_dashboards() -> None:
    assert should_overwrite(None) is True
    assert should_overwrite({MANAGED_FLAG: True, "views": []}) is True
    assert should_overwrite({"views": [{"title": "Custom"}]}) is False


@pytest.mark.asyncio
async def test_setup_without_lovelace_still_loads(hass: HomeAssistant) -> None:
    """Setup succeeds when Lovelace is absent. Entities still register."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.shared_energy_ledger_tenant_flat_1_share") is not None


class _FakeDashboardStore:

    def __init__(self) -> None:
        self.config: dict[str, str] = {"url_path": DASHBOARD_URL_PATH}
        self.saved: dict[str, Any] | None = None

    async def async_load(self, force: bool) -> dict[str, Any]:
        raise HomeAssistantError("empty")

    async def async_save(self, config: dict[str, Any]) -> None:
        self.saved = config


class _FakeLovelace:
    def __init__(self, store: Any) -> None:
        self.dashboards: dict[str, Any] = {DASHBOARD_URL_PATH: store}


@pytest.mark.asyncio
async def test_setup_provisions_managed_dashboard(hass: HomeAssistant) -> None:
    """Setup writes a managed Lovelace dashboard when storage is present."""
    store = _FakeDashboardStore()
    hass.data[LOVELACE_DATA] = _FakeLovelace(store)
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    saved = store.saved
    assert saved is not None
    assert saved.get(MANAGED_FLAG) is True
    assert any(view["path"] == "flat-1" for view in saved["views"])
    tenant_view = next(view for view in saved["views"] if view["path"] == "flat-1")
    assert "sensor.shared_energy_ledger_tenant_flat_1_share" in tenant_view["cards"][0][
        "entities"
    ]


@pytest.mark.asyncio
async def test_setup_skips_when_dashboards_attr_is_not_a_dict(
    hass: HomeAssistant,
) -> None:
    class _BadLovelace:
        dashboards = "not-a-dict"

    hass.data[LOVELACE_DATA] = _BadLovelace()
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


class _KeepStore:
    def __init__(self) -> None:
        self.config: dict[str, str] = {"url_path": DASHBOARD_URL_PATH}
        self.saved: dict[str, Any] | None = None

    async def async_load(self, force: bool) -> dict[str, Any]:
        return {"views": [{"title": "Custom"}]}

    async def async_save(self, config: dict[str, Any]) -> None:
        self.saved = config


@pytest.mark.asyncio
async def test_setup_does_not_overwrite_custom_dashboard(hass: HomeAssistant) -> None:
    store = _KeepStore()
    hass.data[LOVELACE_DATA] = _FakeLovelace(store)
    entry = MockConfigEntry(
        domain=DOMAIN, data=_happy_entry_data(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert store.saved is None


@pytest.mark.asyncio
async def test_setup_dashboard_includes_pv_and_battery_entities(
    hass: HomeAssistant,
) -> None:
    store = _FakeDashboardStore()
    hass.data[LOVELACE_DATA] = _FakeLovelace(store)
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_with_battery(), version=CONFIG_ENTRY_VERSION
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    saved = store.saved
    assert saved is not None
    overview = next(view for view in saved["views"] if view["path"] == "overview")
    titles = [card.get("title") for card in overview["cards"]]
    assert "Grid" in titles
    assert "Battery ledger" in titles
    grid_card = next(card for card in overview["cards"] if card.get("title") == "Grid")
    assert any(
        entity_id.endswith("grid_reconciliation") for entity_id in grid_card["entities"]
    )
    battery_card = next(
        card for card in overview["cards"] if card.get("title") == "Battery ledger"
    )
    assert not any(
        entity_id.endswith("grid_reconciliation")
        for entity_id in battery_card["entities"]
    )
    tenant_view = next(view for view in saved["views"] if view["path"] == "flat-1")
    assert any(
        entity_id.endswith("tenant_flat_1_battery_cost")
        for entity_id in tenant_view["cards"][0]["entities"]
    )
