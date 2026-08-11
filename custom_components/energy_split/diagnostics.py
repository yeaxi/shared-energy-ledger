"""Diagnostics support for the Energy Split integration.

Home Assistant surfaces this endpoint from the config entry page. The output
is intentionally minimal and redacted: it never includes secrets, credentials,
or personally identifying information beyond the tenant display names that the
operator already sees in the UI.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

REDACTED_KEYS: frozenset[str] = frozenset({"unique_id"})


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    The payload is a stable structure suitable for community bug reports.
    """
    data = async_redact_data(dict(entry.data), REDACTED_KEYS)
    options = async_redact_data(dict(entry.options), REDACTED_KEYS)
    return {
        "domain": DOMAIN,
        "version": entry.version,
        "title": entry.title,
        "data": data,
        "options": options,
    }
