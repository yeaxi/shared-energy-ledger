"""Shared pytest fixtures for the Shared Energy Ledger test suite.

The suite is deliberately split into two halves:

* ``tests/unit/`` — pure-Python tests for the accounting core (``ledger``,
  ``allocation``, ``tariff``, ``report``). They never import
  ``homeassistant``. The project runs them on Python 3.14 with the integration
  suite so local and hosted checks use one supported runtime.
* ``tests/integration/`` — tests that use
  ``pytest-homeassistant-custom-component`` to boot a mock Home Assistant
  runtime. The ``enable_custom_integrations`` fixture below makes the
  ``shared_energy_ledger`` component discoverable during those tests.

Fixtures for synthetic data live under ``tests/fixtures/``. They must never
contain data extracted from any real Home Assistant installation.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):  # type: ignore[no-untyped-def]
    """Enable custom integration discovery for every test.

    The upstream fixture is opt-in per test. This wrapper opts in globally so
    integration tests inside ``tests/integration/`` do not have to remember
    to depend on it.
    """
    return enable_custom_integrations
