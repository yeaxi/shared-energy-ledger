"""Config and options flow scaffolding.

The full multi-step flow (currency, grid, PV, battery, whole-building,
tenants, tariff) is implemented in Wave 4 of the migration. This module
currently exposes only the boilerplate the integration needs to satisfy
``config_flow: true`` in the manifest and to keep imports valid.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow

from .const import CONF_CURRENCY, CONFIG_ENTRY_VERSION, DOMAIN


def _user_schema() -> vol.Schema:
    return vol.Schema({vol.Required(CONF_CURRENCY, default="EUR"): vol.All(str, vol.Length(min=3, max=3))})


class EnergySplitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Energy Split."""

    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step.

        A minimal implementation lands here as a placeholder. The full
        multi-step flow is added when the integration reaches the config-flow
        milestone of the migration.
        """
        if user_input is not None:
            return self.async_create_entry(
                title=str(user_input.get(CONF_CURRENCY, "Energy Split")),
                data=user_input,
            )
        return self.async_show_form(step_id="user", data_schema=_user_schema())

    @staticmethod
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return EnergySplitOptionsFlow(entry)


class EnergySplitOptionsFlow(OptionsFlow):
    """Options flow for Energy Split."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Placeholder options flow entry point."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))
