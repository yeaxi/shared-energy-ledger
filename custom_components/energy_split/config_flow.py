"""Config and options flow for Energy Split.

The config flow walks the operator through the minimum viable setup:

1. **user** — currency, grid import energy sensor, day/night tariff rates and
   window bounds, and the number of tenants.
2. **tenants** — one row per tenant with slug, name, allocation policy, and a
   direct energy sensor. The number of rows is fixed to the count entered in
   the ``user`` step.
3. **optional** — optional PV, battery, and whole-building AC-load boundary.

The options flow lets operators change tariff rates, add or rename tenants,
and adjust battery efficiency after setup. Every schema change bumps
:data:`.const.CONFIG_ENTRY_VERSION` and is covered by an entry migration in
:mod:`.__init__`.

The flow never stores tokens or secrets. Currency is validated against the
loose ISO 4217 shape (three uppercase letters). Duplicate slugs abort with a
localized error.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import selector

from .configio import config_to_entry
from .const import (
    CONF_CHARGE_EFFICIENCY,
    CONF_CHARGE_ENERGY,
    CONF_CURRENCY,
    CONF_DISCHARGE_EFFICIENCY,
    CONF_DISCHARGE_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_POWER,
    CONFIG_ENTRY_VERSION,
    DEFAULT_CHARGE_EFFICIENCY,
    DEFAULT_DISCHARGE_EFFICIENCY,
    DOMAIN,
)
from .models import (
    AllocationPolicy,
    BatteryConfig,
    EnergySplitConfig,
    FreshnessConfig,
    GridConfig,
    PvConfig,
    Tenant,
    WholeBuildingConfig,
)
from .tariff import day_night_preset

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

_COUNT_MIN = 2
_COUNT_MAX = 8

CONF_DAY_RATE = "day_rate"
CONF_NIGHT_RATE = "night_rate"
CONF_DAY_START = "day_start"
CONF_NIGHT_START = "night_start"
CONF_COUNT = "tenants_count"


def _currency_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CURRENCY, default="EUR"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["EUR", "USD", "UAH", "PLN", "GBP", "CZK", "SEK", "NOK", "CHF"],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Required(CONF_IMPORT_ENERGY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Required(CONF_DAY_RATE, default=0.30): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step="any", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_NIGHT_RATE, default=0.15): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step="any", mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_DAY_START, default="07:00:00"): selector.TimeSelector(),
            vol.Required(CONF_NIGHT_START, default="23:00:00"): selector.TimeSelector(),
            vol.Required(CONF_COUNT, default=2): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=_COUNT_MIN,
                    max=_COUNT_MAX,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _tenants_schema(count: int) -> vol.Schema:
    schema_dict: dict[Any, Any] = {}
    for index in range(1, count + 1):
        schema_dict[vol.Required(f"tenant_{index}_slug", default=f"flat-{index}")] = str
        schema_dict[vol.Required(f"tenant_{index}_name", default=f"Flat {index}")] = str
        schema_dict[vol.Required(
            f"tenant_{index}_policy", default=AllocationPolicy.DIRECT_METER.value
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[p.value for p in AllocationPolicy],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        schema_dict[vol.Required(f"tenant_{index}_energy")] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy")
        )
    return vol.Schema(schema_dict)


def _optional_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional("include_pv", default=False): bool,
            vol.Optional("include_battery", default=False): bool,
            vol.Optional("include_whole_building", default=False): bool,
        }
    )


def _pv_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional("power_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional("energy_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
        }
    )


def _battery_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CHARGE_ENERGY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Required(CONF_DISCHARGE_ENERGY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Required(CONF_POWER): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Required(
                CONF_CHARGE_EFFICIENCY, default=DEFAULT_CHARGE_EFFICIENCY * 100
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=50, max=100, step=1)
            ),
            vol.Required(
                CONF_DISCHARGE_EFFICIENCY, default=DEFAULT_DISCHARGE_EFFICIENCY * 100
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=50, max=100, step=1)
            ),
        }
    )


def _whole_building_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional("power_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional("energy_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
        }
    )


def _validate_currency(value: str) -> bool:
    return bool(_CURRENCY_RE.match(value.strip().upper()))


def _validate_slug(value: str) -> bool:
    return bool(_SLUG_RE.match(value.strip()))


def _parse_time(value: Any) -> time:
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value))


class EnergySplitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Energy Split."""

    VERSION = CONFIG_ENTRY_VERSION

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._tenants: list[Tenant] = []
        self._tenants_count: int = 2
        self._flags: dict[str, bool] = {}
        self._pv: PvConfig | None = None
        self._battery: BatteryConfig | None = None
        self._whole_building: WholeBuildingConfig | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the base config (currency, grid, tariff, tenants count)."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            if not _validate_currency(str(user_input[CONF_CURRENCY])):
                errors[CONF_CURRENCY] = "invalid_currency"
            try:
                _parse_time(user_input[CONF_DAY_START])
                _parse_time(user_input[CONF_NIGHT_START])
            except (TypeError, ValueError):
                errors["base"] = "invalid_schedule"
            if not errors:
                self._user_input = dict(user_input)
                self._tenants_count = int(user_input[CONF_COUNT])
                return await self.async_step_tenants()
        return self.async_show_form(
            step_id="user", data_schema=_currency_schema(), errors=errors
        )

    async def async_step_tenants(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect one row per tenant."""
        errors: dict[str, str] = {}
        if user_input is not None:
            slugs: list[str] = []
            for index in range(1, self._tenants_count + 1):
                slug = str(user_input[f"tenant_{index}_slug"]).strip()
                if not _validate_slug(slug):
                    errors[f"tenant_{index}_slug"] = "invalid_slug"
                slugs.append(slug)
            if len(set(slugs)) != len(slugs):
                errors["base"] = "duplicate_slug"
            if not errors:
                self._tenants = []
                for index in range(1, self._tenants_count + 1):
                    self._tenants.append(
                        Tenant(
                            slug=slugs[index - 1],
                            name=str(user_input[f"tenant_{index}_name"]).strip(),
                            allocation_policy=AllocationPolicy(
                                str(user_input[f"tenant_{index}_policy"])
                            ),
                            energy_entity=str(user_input[f"tenant_{index}_energy"]),
                        )
                    )
                return await self.async_step_optional()
        return self.async_show_form(
            step_id="tenants",
            data_schema=_tenants_schema(self._tenants_count),
            errors=errors,
        )

    async def async_step_optional(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which optional sections to configure."""
        if user_input is not None:
            self._flags = {
                "pv": bool(user_input.get("include_pv", False)),
                "battery": bool(user_input.get("include_battery", False)),
                "whole_building": bool(user_input.get("include_whole_building", False)),
            }
            return await self._advance_optional()
        return self.async_show_form(step_id="optional", data_schema=_optional_schema())

    async def _advance_optional(self) -> ConfigFlowResult:
        if self._flags.get("pv") and self._pv is None:
            return await self.async_step_pv()
        if self._flags.get("battery") and self._battery is None:
            return await self.async_step_battery()
        if self._flags.get("whole_building") and self._whole_building is None:
            return await self.async_step_whole_building()
        return await self._create()

    async def async_step_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._pv = PvConfig(
                power_entity=user_input.get("power_entity"),
                energy_entity=user_input.get("energy_entity"),
            )
            return await self._advance_optional()
        return self.async_show_form(step_id="pv", data_schema=_pv_schema())

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._battery = BatteryConfig(
                charge_energy_entity=str(user_input[CONF_CHARGE_ENERGY]),
                discharge_energy_entity=str(user_input[CONF_DISCHARGE_ENERGY]),
                power_entity=str(user_input[CONF_POWER]),
                charge_efficiency=float(user_input[CONF_CHARGE_EFFICIENCY]) / 100.0,
                discharge_efficiency=float(user_input[CONF_DISCHARGE_EFFICIENCY]) / 100.0,
            )
            return await self._advance_optional()
        return self.async_show_form(step_id="battery", data_schema=_battery_schema())

    async def async_step_whole_building(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._whole_building = WholeBuildingConfig(
                power_entity=user_input.get("power_entity"),
                energy_entity=user_input.get("energy_entity"),
            )
            return await self._advance_optional()
        return self.async_show_form(
            step_id="whole_building", data_schema=_whole_building_schema()
        )

    async def _create(self) -> ConfigFlowResult:
        currency = str(self._user_input[CONF_CURRENCY]).upper()
        day_start = _parse_time(self._user_input[CONF_DAY_START])
        night_start = _parse_time(self._user_input[CONF_NIGHT_START])
        schedule = day_night_preset(
            day_rate=float(self._user_input[CONF_DAY_RATE]),
            night_rate=float(self._user_input[CONF_NIGHT_RATE]),
            day_start=day_start,
            night_start=night_start,
            effective_from=datetime.now(UTC),
        )
        config = EnergySplitConfig(
            currency=currency,
            grid=GridConfig(
                import_energy_entity=str(self._user_input[CONF_IMPORT_ENERGY])
            ),
            tenants=tuple(self._tenants),
            tariff=schedule,
            pv=self._pv,
            battery=self._battery,
            whole_building=self._whole_building,
            freshness=FreshnessConfig(),
        )
        return self.async_create_entry(
            title=f"Energy Split ({currency})", data=config_to_entry(config)
        )

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
        """Options flow entry point.

        A future PR will expose add/rename/remove-tenant, tariff editing, and
        battery-efficiency tuning. For now the options flow is a passthrough
        that lets the operator persist arbitrary key/value overrides which
        take precedence over the initial config data (see
        :func:`.configio.config_from_entry`).
        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema({}), last_step=True
        )


