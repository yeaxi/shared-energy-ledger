"""Base entity classes for the Shared Energy Ledger integration.

All entities extend :class:`SharedEnergyLedgerEntity` (or its coordinator-driven
variant) so they share device registration, unique_id policy, and
availability propagation. This module never contains rendering logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SharedEnergyLedgerCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def object_id_for(key: str, tenant_slug: str | None = None) -> str:
    """Return the entity object_id for a hub or tenant resource.

    Tenant slugs chosen at config time are the prefix used in entity IDs, as
    specified in ``REQUIREMENTS.md`` A2.3 (for example
    ``shared_energy_ledger_tenant_flat_1_share``). Hyphens in the slug become
    underscores because Home Assistant object IDs cannot contain hyphens.
    ``unique_id`` stays on the immutable ``tenant_id``; only the suggested
    entity ID uses the slug.
    """
    if tenant_slug is None:
        return f"{DOMAIN}_{key}"
    slug = tenant_slug.replace("-", "_")
    suffix = key.removeprefix("tenant_")
    return f"{DOMAIN}_tenant_{slug}_{suffix}"


def hub_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the hub device for this config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "Shared Energy Ledger",
        manufacturer="Shared Energy Ledger",
        model="Cooperative energy accounting",
        entry_type=None,
    )


def tenant_device_info(entry: ConfigEntry, tenant_id: str, name: str) -> DeviceInfo:
    """Return a via-hub device named after the tenant display name."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{tenant_id}")},
        name=name,
        manufacturer="Shared Energy Ledger",
        model="Cooperative tenant",
        via_device=(DOMAIN, entry.entry_id),
    )


class SharedEnergyLedgerEntity(CoordinatorEntity[SharedEnergyLedgerCoordinator]):
    """Base class for every Shared Energy Ledger entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SharedEnergyLedgerCoordinator,
        translation_key: str,
        resource_slug: str,
        *,
        domain: str,
        tenant_slug: str | None = None,
        tenant_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        entry: ConfigEntry = coordinator.config_entry
        self._entry_id = entry.entry_id
        self._resource_slug = resource_slug
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.entry_id}:{resource_slug}:{translation_key}"
        if tenant_slug is not None and tenant_name is not None:
            self._attr_device_info = tenant_device_info(entry, resource_slug, tenant_name)
        else:
            self._attr_device_info = hub_device_info(entry)
        self.entity_id = f"{domain}.{object_id_for(translation_key, tenant_slug)}"


__all__ = [
    "SharedEnergyLedgerEntity",
    "hub_device_info",
    "object_id_for",
    "tenant_device_info",
]
