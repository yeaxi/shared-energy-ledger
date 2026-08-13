"""Config and options flow for Shared Energy Ledger.

The config flow collects the meters and price sensors the coordinator actually
reads:

1. **user** — currency, grid import energy sensor, grid import price sensor.
2. **optional** — which of PV, battery, and whole-building boundary to add.
3. **pv / battery / whole_building** — the selected optional sections.
4. **tenant** — one tenant per screen, repeated until the operator finishes
   (minimum two). Each tenant gets a stable ``tenant_id`` used in entity
   ``unique_id``s; the editable slug is only a display label.

Pricing comes from operator-provided ``<currency>/kWh`` sensors, so there is no
tariff editor. Every runtime-changeable parameter lives in the options flow.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import selector

from .configio import CONF_TENANT_ID, config_to_entry
from .const import (
    CONF_CHARGE_EFFICIENCY,
    CONF_CHARGE_ENERGY,
    CONF_CURRENCY,
    CONF_DISCHARGE_EFFICIENCY,
    CONF_DISCHARGE_ENERGY,
    CONF_ENERGY,
    CONF_IMPORT_ENERGY,
    CONF_IMPORT_PRICE,
    CONF_POWER,
    CONF_PV_PRICE,
    CONF_PV_ZERO_COST,
    CONF_TENANT_ALLOCATION,
    CONF_TENANT_NAME,
    CONF_TENANT_SLUG,
    DEFAULT_CHARGE_EFFICIENCY,
    DEFAULT_DISCHARGE_EFFICIENCY,
    DOMAIN,
)
from .models import (
    AllocationPolicy,
    BatteryConfig,
    FreshnessConfig,
    GridConfig,
    PvConfig,
    SharedEnergyLedgerConfig,
    Tenant,
    WholeBuildingConfig,
)

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

_MIN_TENANTS = 2

_CURRENCIES = ["EUR", "USD", "UAH", "PLN", "GBP", "CZK", "SEK", "NOK", "CHF"]


def _validate_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug))


def _energy_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
    )


def _price_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))


def _power_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="power")
    )


def _policy_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[p.value for p in AllocationPolicy],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="allocation_policy",
        )
    )


class SharedEnergyLedgerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Shared Energy Ledger."""

    VERSION = 2

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._flags: dict[str, bool] = {}
        self._pv: PvConfig | None = None
        self._battery: BatteryConfig | None = None
        self._whole_building: WholeBuildingConfig | None = None
        self._tenants: list[Tenant] = []
        self._reconfiguring = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect currency and the grid import energy and price sensors."""
        if self._async_current_entries() and not self._reconfiguring:
            return self.async_abort(reason="single_instance_allowed")
        errors: dict[str, str] = {}
        if user_input is not None:
            currency = str(user_input[CONF_CURRENCY]).upper()
            if not _CURRENCY_RE.match(currency):
                errors[CONF_CURRENCY] = "invalid_currency"
            if not errors:
                self._user_input = dict(user_input)
                self._user_input[CONF_CURRENCY] = currency
                return await self.async_step_optional()
        schema = vol.Schema(
            {
                vol.Required(CONF_CURRENCY, default="EUR"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_CURRENCIES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Required(CONF_IMPORT_ENERGY): _energy_selector(),
                vol.Required(CONF_IMPORT_PRICE): _price_selector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
        schema = vol.Schema(
            {
                vol.Optional("include_pv", default=False): bool,
                vol.Optional("include_battery", default=False): bool,
                vol.Optional("include_whole_building", default=False): bool,
            }
        )
        return self.async_show_form(step_id="optional", data_schema=schema)

    async def _advance_optional(self) -> ConfigFlowResult:
        if self._flags.get("pv") and self._pv is None:
            return await self.async_step_pv()
        if self._flags.get("battery") and self._battery is None:
            return await self.async_step_battery()
        if self._flags.get("whole_building") and self._whole_building is None:
            return await self.async_step_whole_building()
        return await self.async_step_tenant()

    async def async_step_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the PV aggregate energy sensor and its price."""
        errors: dict[str, str] = {}
        if user_input is not None:
            zero_cost = bool(user_input.get(CONF_PV_ZERO_COST, False))
            price_entity = user_input.get(CONF_PV_PRICE)
            if not zero_cost and not price_entity:
                errors[CONF_PV_PRICE] = "pv_price_required"
            if not errors:
                self._pv = PvConfig(
                    energy_entity=str(user_input[CONF_ENERGY]),
                    price_entity=price_entity,
                    zero_cost=zero_cost,
                    power_entity=user_input.get(CONF_POWER),
                )
                return await self._advance_optional()
        schema = vol.Schema(
            {
                vol.Required(CONF_ENERGY): _energy_selector(),
                vol.Optional(CONF_PV_ZERO_COST, default=False): bool,
                vol.Optional(CONF_PV_PRICE): _price_selector(),
                vol.Optional(CONF_POWER): _power_selector(),
            }
        )
        return self.async_show_form(step_id="pv", data_schema=schema, errors=errors)

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the battery counters and efficiencies."""
        if user_input is not None:
            self._battery = BatteryConfig(
                charge_energy_entity=str(user_input[CONF_CHARGE_ENERGY]),
                discharge_energy_entity=str(user_input[CONF_DISCHARGE_ENERGY]),
                power_entity=str(user_input[CONF_POWER]),
                charge_efficiency=float(user_input[CONF_CHARGE_EFFICIENCY]) / 100.0,
                discharge_efficiency=float(user_input[CONF_DISCHARGE_EFFICIENCY]) / 100.0,
            )
            return await self._advance_optional()
        schema = vol.Schema(
            {
                vol.Required(CONF_CHARGE_ENERGY): _energy_selector(),
                vol.Required(CONF_DISCHARGE_ENERGY): _energy_selector(),
                vol.Required(CONF_POWER): _power_selector(),
                vol.Required(
                    CONF_CHARGE_EFFICIENCY, default=DEFAULT_CHARGE_EFFICIENCY * 100
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=50, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Required(
                    CONF_DISCHARGE_EFFICIENCY, default=DEFAULT_DISCHARGE_EFFICIENCY * 100
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=50, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
            }
        )
        return self.async_show_form(step_id="battery", data_schema=schema)

    async def async_step_whole_building(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the optional whole-building boundary meter."""
        if user_input is not None:
            self._whole_building = WholeBuildingConfig(
                energy_entity=user_input.get(CONF_ENERGY),
                power_entity=user_input.get(CONF_POWER),
            )
            return await self._advance_optional()
        schema = vol.Schema(
            {
                vol.Optional(CONF_ENERGY): _energy_selector(),
                vol.Optional(CONF_POWER): _power_selector(),
            }
        )
        return self.async_show_form(step_id="whole_building", data_schema=schema)

    async def async_step_tenant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a single tenant; repeat until the operator finishes."""
        errors: dict[str, str] = {}
        existing = {t.slug for t in self._tenants}
        if user_input is not None:
            slug = str(user_input[CONF_TENANT_SLUG]).strip()
            if not _validate_slug(slug):
                errors[CONF_TENANT_SLUG] = "invalid_slug"
            elif slug in existing:
                errors[CONF_TENANT_SLUG] = "duplicate_slug"
            if not errors:
                self._tenants.append(
                    Tenant(
                        tenant_id=uuid4().hex,
                        slug=slug,
                        name=str(user_input[CONF_TENANT_NAME]).strip() or slug,
                        allocation_policy=AllocationPolicy(str(user_input[CONF_TENANT_ALLOCATION])),
                        energy_entity=user_input.get(CONF_ENERGY),
                        power_entity=user_input.get(CONF_POWER),
                    )
                )
                if user_input.get("add_another", True) or len(self._tenants) < _MIN_TENANTS:
                    return await self.async_step_tenant()
                return await self._create()
        index = len(self._tenants) + 1
        schema = vol.Schema(
            {
                vol.Required(CONF_TENANT_SLUG, default=f"flat-{index}"): str,
                vol.Required(CONF_TENANT_NAME, default=f"Flat {index}"): str,
                vol.Required(
                    CONF_TENANT_ALLOCATION, default=AllocationPolicy.DIRECT_METER.value
                ): _policy_selector(),
                vol.Optional(CONF_ENERGY): _energy_selector(),
                vol.Optional(CONF_POWER): _power_selector(),
                vol.Optional("add_another", default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="tenant",
            data_schema=schema,
            errors=errors,
            description_placeholders={"count": str(len(self._tenants))},
        )

    async def _create(self) -> ConfigFlowResult:
        currency = str(self._user_input[CONF_CURRENCY]).upper()
        config = SharedEnergyLedgerConfig(
            currency=currency,
            grid=GridConfig(
                import_energy_entity=str(self._user_input[CONF_IMPORT_ENERGY]),
                import_price_entity=str(self._user_input[CONF_IMPORT_PRICE]),
            ),
            tenants=tuple(self._tenants),
            pv=self._pv,
            battery=self._battery,
            whole_building=self._whole_building,
            freshness=FreshnessConfig(),
        )
        title = f"Shared Energy Ledger ({currency})"
        data = config_to_entry(config)
        if self._reconfiguring:
            existing = self._async_current_entries()[0]
            return self.async_update_reload_and_abort(
                existing, data=data, title=title, reason="reconfigure_successful"
            )
        return self.async_create_entry(title=title, data=data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-run the setup wizard to swap meters or price sensors."""
        self._reconfiguring = True
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return SharedEnergyLedgerOptionsFlow(entry)


class SharedEnergyLedgerOptionsFlow(OptionsFlow):
    """Menu-driven options flow: add, edit, remove, reorder tenants; freshness."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._selected_slug: str | None = None

    def _current_tenants(self) -> list[dict[str, Any]]:
        tenants = list(
            self.entry.options.get("tenants") or self.entry.data.get("tenants") or []
        )
        return [dict(t) for t in tenants]

    def _finalize(self, tenants: list[dict[str, Any]] | None = None,
                  freshness: dict[str, int] | None = None) -> ConfigFlowResult:
        merged = dict(self.entry.options)
        if tenants is not None:
            merged["tenants"] = tenants
        if freshness is not None:
            merged["freshness"] = freshness
        return self.async_create_entry(title="", data=merged)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_tenant", "edit_tenant", "remove_tenant", "reorder", "freshness"],
        )

    async def async_step_add_tenant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        tenants = self._current_tenants()
        existing = {t.get("slug") for t in tenants}
        if user_input is not None:
            slug = str(user_input[CONF_TENANT_SLUG]).strip()
            if not _validate_slug(slug):
                errors[CONF_TENANT_SLUG] = "invalid_slug"
            elif slug in existing:
                errors[CONF_TENANT_SLUG] = "duplicate_slug"
            if not errors:
                tenants.append(
                    {
                        CONF_TENANT_ID: uuid4().hex,
                        CONF_TENANT_SLUG: slug,
                        CONF_TENANT_NAME: str(user_input[CONF_TENANT_NAME]).strip() or slug,
                        CONF_TENANT_ALLOCATION: user_input[CONF_TENANT_ALLOCATION],
                        CONF_ENERGY: user_input.get(CONF_ENERGY),
                        CONF_POWER: user_input.get(CONF_POWER),
                        "shared_loads": [],
                    }
                )
                return self._finalize(tenants=tenants)
        schema = vol.Schema(
            {
                vol.Required(CONF_TENANT_SLUG): str,
                vol.Required(CONF_TENANT_NAME): str,
                vol.Required(
                    CONF_TENANT_ALLOCATION, default=AllocationPolicy.DIRECT_METER.value
                ): _policy_selector(),
                vol.Optional(CONF_ENERGY): _energy_selector(),
                vol.Optional(CONF_POWER): _power_selector(),
            }
        )
        return self.async_show_form(step_id="add_tenant", data_schema=schema, errors=errors)

    async def async_step_edit_tenant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        tenants = self._current_tenants()
        if not tenants:
            return self.async_abort(reason="no_tenants")
        if user_input is not None and self._selected_slug is None:
            self._selected_slug = str(user_input["slug"])
            return await self.async_step_edit_tenant_details()
        options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        schema = vol.Schema(
            {
                vol.Required("slug"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(step_id="edit_tenant", data_schema=schema)

    async def async_step_edit_tenant_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._selected_slug is not None
        tenants = self._current_tenants()
        target = next((t for t in tenants if t["slug"] == self._selected_slug), None)
        if target is None:
            self._selected_slug = None
            return self.async_abort(reason="unknown_tenant")
        if user_input is not None:
            new_name = str(user_input[CONF_TENANT_NAME]).strip()
            if new_name:
                target[CONF_TENANT_NAME] = new_name
            target[CONF_TENANT_ALLOCATION] = user_input[CONF_TENANT_ALLOCATION]
            if user_input.get(CONF_ENERGY) is not None:
                target[CONF_ENERGY] = user_input.get(CONF_ENERGY)
            if user_input.get(CONF_POWER) is not None:
                target[CONF_POWER] = user_input.get(CONF_POWER)
            self._selected_slug = None
            return self._finalize(tenants=tenants)
        schema = vol.Schema(
            {
                vol.Required(CONF_TENANT_NAME, default=target.get("name", "")): str,
                vol.Required(
                    CONF_TENANT_ALLOCATION,
                    default=target.get("allocation_policy", AllocationPolicy.DIRECT_METER.value),
                ): _policy_selector(),
                vol.Optional(CONF_ENERGY): _energy_selector(),
                vol.Optional(CONF_POWER): _power_selector(),
            }
        )
        return self.async_show_form(
            step_id="edit_tenant_details",
            data_schema=schema,
            description_placeholders={"slug": self._selected_slug},
        )

    async def async_step_remove_tenant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        tenants = self._current_tenants()
        if len(tenants) <= _MIN_TENANTS:
            return self.async_abort(reason="minimum_tenants")
        if user_input is not None:
            slug = str(user_input["slug"])
            tenants = [t for t in tenants if t["slug"] != slug]
            return self._finalize(tenants=tenants)
        options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        schema = vol.Schema(
            {
                vol.Required("slug"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_tenant", data_schema=schema)

    async def async_step_reorder(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        tenants = self._current_tenants()
        by_slug = {t["slug"]: t for t in tenants}
        if user_input is not None:
            order = list(user_input.get("order", []))
            if sorted(order) == sorted(by_slug):
                reordered = [by_slug[s] for s in order]
                return self._finalize(tenants=reordered)
            return self.async_abort(reason="reorder_incomplete")
        options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        schema = vol.Schema(
            {
                vol.Required("order", default=[t["slug"] for t in tenants]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                        multiple=True,
                    )
                )
            }
        )
        return self.async_show_form(step_id="reorder", data_schema=schema)

    async def async_step_freshness(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        current = dict(
            self.entry.options.get("freshness") or self.entry.data.get("freshness") or {}
        )
        if user_input is not None:
            return self._finalize(
                freshness={
                    "power_max_age_s": int(user_input["power_max_age_s"]),
                    "energy_max_age_s": int(user_input["energy_max_age_s"]),
                    "price_max_age_s": int(user_input["price_max_age_s"]),
                    "battery_ledger_max_age_s": int(user_input["battery_ledger_max_age_s"]),
                    "alignment_skew_s": int(user_input["alignment_skew_s"]),
                }
            )
        schema = vol.Schema(
            {
                vol.Required(
                    "power_max_age_s", default=int(current.get("power_max_age_s", 180))
                ): vol.All(int, vol.Range(min=10, max=3600)),
                vol.Required(
                    "energy_max_age_s", default=int(current.get("energy_max_age_s", 1800))
                ): vol.All(int, vol.Range(min=60, max=86400)),
                vol.Required(
                    "price_max_age_s", default=int(current.get("price_max_age_s", 3600))
                ): vol.All(int, vol.Range(min=60, max=86400)),
                vol.Required(
                    "battery_ledger_max_age_s",
                    default=int(current.get("battery_ledger_max_age_s", 900)),
                ): vol.All(int, vol.Range(min=60, max=86400)),
                vol.Required(
                    "alignment_skew_s", default=int(current.get("alignment_skew_s", 180))
                ): vol.All(int, vol.Range(min=10, max=3600)),
            }
        )
        return self.async_show_form(step_id="freshness", data_schema=schema)


__all__ = ["SharedEnergyLedgerConfigFlow", "SharedEnergyLedgerOptionsFlow"]
