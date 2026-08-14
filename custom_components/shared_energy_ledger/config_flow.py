"""Config and options flow for Shared Energy Ledger.

The config flow collects the meters and price sensors the coordinator actually
reads:

1. **user** — currency, grid import energy sensor, grid import price sensor.
2. **optional** — which of PV, battery, and whole-building boundary to add.
3. **pv / battery / whole_building** — the selected optional sections.
4. **tenant** — one tenant per screen, repeated until the operator finishes
   (minimum two). Each tenant gets a stable ``tenant_id`` used in entity
   ``unique_id``s; the editable slug is only a display label.

Every runtime-changeable parameter lives in the options flow.
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
    CONF_INITIAL_STOCK_COST,
    CONF_INITIAL_STOCK_KWH,
    CONF_LOAD_ID,
    CONF_POWER,
    CONF_PV_PRICE,
    CONF_PV_ZERO_COST,
    CONF_SHARED_LOAD_HOST,
    CONF_TENANT_ALLOCATION,
    CONF_TENANT_NAME,
    CONF_TENANT_SHARED_LOADS,
    CONF_TENANT_SLUG,
    DEFAULT_CHARGE_EFFICIENCY,
    DEFAULT_DISCHARGE_EFFICIENCY,
    DOMAIN,
)
from .ledger import validate_boundary
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

    VERSION = 3

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
                )
                return await self._advance_optional()
        schema = vol.Schema(
            {
                vol.Required(CONF_ENERGY): _energy_selector(),
                vol.Optional(CONF_PV_ZERO_COST, default=False): bool,
                vol.Optional(CONF_PV_PRICE): _price_selector(),
            }
        )
        return self.async_show_form(step_id="pv", data_schema=schema, errors=errors)

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the battery counters, efficiencies, and initial priced stock."""
        errors: dict[str, str] = {}
        if user_input is not None:
            stock_kwh = float(user_input[CONF_INITIAL_STOCK_KWH])
            stock_cost = float(user_input[CONF_INITIAL_STOCK_COST])
            if not validate_boundary(stock_kwh, stock_cost):
                errors["base"] = "invalid_ledger_boundary"
            else:
                self._battery = BatteryConfig(
                    charge_energy_entity=str(user_input[CONF_CHARGE_ENERGY]),
                    discharge_energy_entity=str(user_input[CONF_DISCHARGE_ENERGY]),
                    power_entity=str(user_input[CONF_POWER]),
                    charge_efficiency=float(user_input[CONF_CHARGE_EFFICIENCY]) / 100.0,
                    discharge_efficiency=float(user_input[CONF_DISCHARGE_EFFICIENCY]) / 100.0,
                    initial_stock_kwh=stock_kwh,
                    initial_stock_cost=stock_cost,
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
                vol.Required(CONF_INITIAL_STOCK_KWH, default=0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required(CONF_INITIAL_STOCK_COST, default=0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.01, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="battery", data_schema=schema, errors=errors)

    async def async_step_whole_building(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the optional whole-building boundary meter."""
        if user_input is not None:
            self._whole_building = WholeBuildingConfig(
                energy_entity=user_input.get(CONF_ENERGY),
            )
            return await self._advance_optional()
        schema = vol.Schema(
            {
                vol.Optional(CONF_ENERGY): _energy_selector(),
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
    """Menu-driven options flow: tenants, shared loads, and freshness."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._selected_slug: str | None = None
        self._shared_load_owner: str | None = None
        self._selected_load_id: str | None = None

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

    def _tenant_slugs(self, tenants: list[dict[str, Any]]) -> set[str]:
        return {str(t["slug"]) for t in tenants}

    def _iter_shared_loads(
        self, tenants: list[dict[str, Any]]
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for tenant in tenants:
            for load in tenant.get(CONF_TENANT_SHARED_LOADS) or []:
                if isinstance(load, dict) and load.get(CONF_LOAD_ID):
                    pairs.append((tenant, dict(load)))
        return pairs

    def _load_select_options(
        self, tenants: list[dict[str, Any]]
    ) -> list[selector.SelectOptionDict]:
        options: list[selector.SelectOptionDict] = []
        for tenant, load in self._iter_shared_loads(tenants):
            label = f'{load.get("label", "shared-load")} ({tenant["slug"]})'
            options.append(
                selector.SelectOptionDict(value=str(load[CONF_LOAD_ID]), label=label)
            )
        return options

    def _find_load(
        self, tenants: list[dict[str, Any]], load_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        for tenant, load in self._iter_shared_loads(tenants):
            if str(load.get(CONF_LOAD_ID)) == load_id:
                return tenant, load
        return None

    def _validate_host(
        self, host: object, tenants: list[dict[str, Any]]
    ) -> tuple[str | None, str | None]:
        if host is None or host == "":
            return None, None
        host_slug = str(host)
        if host_slug not in self._tenant_slugs(tenants):
            return None, "invalid_host"
        return host_slug, None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_tenant",
                "edit_tenant",
                "remove_tenant",
                "reorder",
                "shared_load",
                "edit_shared_load",
                "remove_shared_load",
                "reassign_owner",
                "freshness",
            ],
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
            target.pop(CONF_POWER, None)
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
        errors: dict[str, str] = {}
        if user_input is not None:
            slug = str(user_input["slug"])
            if not user_input.get("confirm"):
                errors["confirm"] = "confirm_required"
            else:
                host_refs = [
                    load
                    for tenant, load in self._iter_shared_loads(tenants)
                    if tenant["slug"] != slug
                    and load.get(CONF_SHARED_LOAD_HOST) == slug
                ]
                if host_refs:
                    return self.async_abort(reason="tenant_is_shared_load_host")
                remaining = []
                for tenant in tenants:
                    if tenant["slug"] == slug:
                        continue
                    remaining.append(tenant)
                return self._finalize(tenants=remaining)
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
                ),
                vol.Required("confirm", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="remove_tenant", data_schema=schema, errors=errors
        )

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

    async def async_step_shared_load(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the owning tenant for a new shared load."""
        tenants = self._current_tenants()
        if not tenants:
            return self.async_abort(reason="no_tenants")
        if user_input is not None:
            owner = str(user_input["owner"])
            if owner not in self._tenant_slugs(tenants):
                return self.async_abort(reason="unknown_tenant")
            self._shared_load_owner = owner
            return await self.async_step_shared_load_details()
        options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        schema = vol.Schema(
            {
                vol.Required("owner"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(step_id="shared_load", data_schema=schema)

    async def async_step_shared_load_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Attach a shared load to the selected owner with optional host meter."""
        assert self._shared_load_owner is not None
        tenants = self._current_tenants()
        owner = next((t for t in tenants if t["slug"] == self._shared_load_owner), None)
        if owner is None:
            self._shared_load_owner = None
            return self.async_abort(reason="unknown_tenant")
        errors: dict[str, str] = {}
        if user_input is not None:
            host_slug, host_error = self._validate_host(
                user_input.get(CONF_SHARED_LOAD_HOST), tenants
            )
            if host_error:
                errors[CONF_SHARED_LOAD_HOST] = host_error
            else:
                load: dict[str, Any] = {
                    "label": str(user_input["label"]).strip() or "shared-load",
                    CONF_LOAD_ID: uuid4().hex,
                    CONF_ENERGY: user_input.get(CONF_ENERGY),
                }
                if host_slug is not None:
                    load[CONF_SHARED_LOAD_HOST] = host_slug
                loads = list(owner.get(CONF_TENANT_SHARED_LOADS) or [])
                loads.append(load)
                owner[CONF_TENANT_SHARED_LOADS] = loads
                self._shared_load_owner = None
                return self._finalize(tenants=tenants)
        host_options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        schema = vol.Schema(
            {
                vol.Required("label"): str,
                vol.Optional(CONF_ENERGY): _energy_selector(),
                vol.Optional(CONF_SHARED_LOAD_HOST): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=host_options, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="shared_load_details",
            data_schema=schema,
            errors=errors,
            description_placeholders={"owner": self._shared_load_owner},
        )

    async def async_step_edit_shared_load(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        tenants = self._current_tenants()
        options = self._load_select_options(tenants)
        if not options:
            return self.async_abort(reason="no_shared_loads")
        if user_input is not None and self._selected_load_id is None:
            self._selected_load_id = str(user_input[CONF_LOAD_ID])
            return await self.async_step_edit_shared_load_details()
        schema = vol.Schema(
            {
                vol.Required(CONF_LOAD_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(step_id="edit_shared_load", data_schema=schema)

    async def async_step_edit_shared_load_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._selected_load_id is not None
        tenants = self._current_tenants()
        found = self._find_load(tenants, self._selected_load_id)
        if found is None:
            self._selected_load_id = None
            return self.async_abort(reason="unknown_shared_load")
        owner, load = found
        errors: dict[str, str] = {}
        if user_input is not None:
            host_raw = (
                user_input[CONF_SHARED_LOAD_HOST]
                if CONF_SHARED_LOAD_HOST in user_input
                else load.get(CONF_SHARED_LOAD_HOST)
            )
            host_slug, host_error = self._validate_host(host_raw, tenants)
            if host_error:
                errors[CONF_SHARED_LOAD_HOST] = host_error
            else:
                updated: dict[str, Any] = {
                    "label": str(user_input["label"]).strip() or str(load.get("label")),
                    CONF_LOAD_ID: load[CONF_LOAD_ID],
                    CONF_ENERGY: user_input.get(CONF_ENERGY, load.get(CONF_ENERGY)),
                }
                if host_slug is not None:
                    updated[CONF_SHARED_LOAD_HOST] = host_slug
                loads = list(owner.get(CONF_TENANT_SHARED_LOADS) or [])
                owner[CONF_TENANT_SHARED_LOADS] = [
                    updated if item.get(CONF_LOAD_ID) == load[CONF_LOAD_ID] else item
                    for item in loads
                ]
                self._selected_load_id = None
                return self._finalize(tenants=tenants)
        host_options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        schema_dict: dict[Any, Any] = {
            vol.Required("label", default=str(load.get("label", ""))): str,
            vol.Optional(CONF_ENERGY): _energy_selector(),
            vol.Optional(CONF_SHARED_LOAD_HOST): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=host_options, mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
        }
        return self.async_show_form(
            step_id="edit_shared_load_details",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "load_id": str(load[CONF_LOAD_ID]),
                "owner": str(owner["slug"]),
            },
        )

    async def async_step_remove_shared_load(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        tenants = self._current_tenants()
        options = self._load_select_options(tenants)
        if not options:
            return self.async_abort(reason="no_shared_loads")
        errors: dict[str, str] = {}
        if user_input is not None:
            load_id = str(user_input[CONF_LOAD_ID])
            if not user_input.get("confirm"):
                errors["confirm"] = "confirm_required"
            else:
                found = self._find_load(tenants, load_id)
                if found is None:
                    return self.async_abort(reason="unknown_shared_load")
                owner, _load = found
                owner[CONF_TENANT_SHARED_LOADS] = [
                    item
                    for item in (owner.get(CONF_TENANT_SHARED_LOADS) or [])
                    if item.get(CONF_LOAD_ID) != load_id
                ]
                return self._finalize(tenants=tenants)
        schema = vol.Schema(
            {
                vol.Required(CONF_LOAD_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                ),
                vol.Required("confirm", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="remove_shared_load", data_schema=schema, errors=errors
        )

    async def async_step_reassign_owner(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        tenants = self._current_tenants()
        options = self._load_select_options(tenants)
        if not options:
            return self.async_abort(reason="no_shared_loads")
        if user_input is not None and self._selected_load_id is None:
            self._selected_load_id = str(user_input[CONF_LOAD_ID])
            return await self.async_step_reassign_owner_details()
        schema = vol.Schema(
            {
                vol.Required(CONF_LOAD_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(step_id="reassign_owner", data_schema=schema)

    async def async_step_reassign_owner_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._selected_load_id is not None
        tenants = self._current_tenants()
        found = self._find_load(tenants, self._selected_load_id)
        if found is None:
            self._selected_load_id = None
            return self.async_abort(reason="unknown_shared_load")
        current_owner, load = found
        errors: dict[str, str] = {}
        if user_input is not None:
            new_owner_slug = str(user_input["owner"])
            new_owner = next((t for t in tenants if t["slug"] == new_owner_slug), None)
            if new_owner is None:
                errors["owner"] = "unknown_tenant"
            else:
                host_slug = load.get(CONF_SHARED_LOAD_HOST)
                if host_slug is not None and host_slug not in self._tenant_slugs(tenants):
                    load = dict(load)
                    load.pop(CONF_SHARED_LOAD_HOST, None)
                current_owner[CONF_TENANT_SHARED_LOADS] = [
                    item
                    for item in (current_owner.get(CONF_TENANT_SHARED_LOADS) or [])
                    if item.get(CONF_LOAD_ID) != load[CONF_LOAD_ID]
                ]
                dest = list(new_owner.get(CONF_TENANT_SHARED_LOADS) or [])
                dest.append(load)
                new_owner[CONF_TENANT_SHARED_LOADS] = dest
                self._selected_load_id = None
                return self._finalize(tenants=tenants)
        owner_options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        schema = vol.Schema(
            {
                vol.Required("owner", default=str(current_owner["slug"])): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=owner_options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="reassign_owner_details",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "load_id": str(load[CONF_LOAD_ID]),
                "owner": str(current_owner["slug"]),
            },
        )

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
