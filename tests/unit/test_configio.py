"""Unit tests for config-entry serialization (requirements I3, I9)."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.shared_energy_ledger.configio import (
    ConfigError,
    config_from_entry,
    config_to_entry,
)
from custom_components.shared_energy_ledger.models import AllocationPolicy


def _entry() -> dict[str, Any]:
    return {
        "currency": "EUR",
        "grid": {
            "import_energy_entity": "sensor.grid_import",
            "import_price_entity": "sensor.grid_price",
        },
        "tenants": [
            {
                "tenant_id": "id-a",
                "slug": "flat-1",
                "name": "Flat 1",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.flat_1_energy",
            },
            {
                "tenant_id": "id-b",
                "slug": "flat-2",
                "name": "Flat 2",
                "allocation_policy": "direct_meter",
                "energy_entity": "sensor.flat_2_energy",
            },
        ],
    }


def test_round_trip_preserves_grid_price_and_tenant_id() -> None:
    config = config_from_entry(_entry(), {})
    assert config.grid.import_price_entity == "sensor.grid_price"
    assert config.tenants[0].tenant_id == "id-a"
    dumped = config_to_entry(config)
    reloaded = config_from_entry(dumped, {})
    assert reloaded.tenants[0].tenant_id == "id-a"
    assert reloaded.tenants[1].allocation_policy is AllocationPolicy.DIRECT_METER


def test_missing_grid_price_is_rejected() -> None:
    entry = _entry()
    del entry["grid"]["import_price_entity"]
    with pytest.raises(ConfigError):
        config_from_entry(entry, {})


def test_fewer_than_two_tenants_rejected() -> None:
    entry = _entry()
    entry["tenants"] = entry["tenants"][:1]
    with pytest.raises(ConfigError):
        config_from_entry(entry, {})


def test_duplicate_slug_rejected() -> None:
    entry = _entry()
    entry["tenants"][1]["slug"] = "flat-1"
    with pytest.raises(ConfigError):
        config_from_entry(entry, {})


def test_pv_requires_price_or_zero_cost() -> None:
    entry = _entry()
    entry["pv"] = {"energy_entity": "sensor.pv"}
    with pytest.raises(ConfigError):
        config_from_entry(entry, {})
    entry["pv"] = {"energy_entity": "sensor.pv", "zero_cost": True}
    config = config_from_entry(entry, {})
    assert config.pv is not None
    assert config.pv.zero_cost is True
    entry["pv"] = {"energy_entity": "sensor.pv", "price_entity": "sensor.pv_price"}
    config = config_from_entry(entry, {})
    assert config.pv is not None
    assert config.pv.price_entity == "sensor.pv_price"


def test_i9_tenant_id_defaults_to_slug_for_legacy_entries() -> None:
    """A migrated v1 tenant with no tenant_id falls back to the slug."""
    entry = _entry()
    for tenant in entry["tenants"]:
        del tenant["tenant_id"]
    config = config_from_entry(entry, {})
    assert config.tenants[0].tenant_id == "flat-1"


def test_options_override_tenants() -> None:
    entry = _entry()
    options = {"tenants": entry["tenants"] + [
        {
            "tenant_id": "id-c",
            "slug": "flat-3",
            "name": "Flat 3",
            "allocation_policy": "direct_meter",
            "energy_entity": "sensor.flat_3_energy",
        }
    ]}
    config = config_from_entry(entry, options)
    assert len(config.tenants) == 3
