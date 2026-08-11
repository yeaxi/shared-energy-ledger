"""Service registration for Energy Split.

The concrete service handlers depend on ``report.py`` and ``ledger.py``; they
are wired in the Wave 3/4 milestones. This module currently exposes a
placeholder registration entry point so ``__init__.py`` and tests can import
it.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services. Placeholder until Wave 4."""
    return
