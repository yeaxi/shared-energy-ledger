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
        self._reconfiguring: bool = False

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rerun the initial flow to swap grid/tariff/tenant sources.

        Reconfigure is preferred over reauth for Energy Split because the
        integration has no external credentials; the operator just wants to
        replace the entity IDs when an upstream device is renamed.
        """
        self._reconfiguring = True
        return await self.async_step_user(user_input)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the base config (currency, grid, tariff, tenants count)."""
        if not self._reconfiguring and self._async_current_entries():
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
        title = f"Energy Split ({currency})"
        data = config_to_entry(config)
        if self._reconfiguring:
            existing = self._async_current_entries()[0]
            return self.async_update_reload_and_abort(
                existing, data=data, title=title, reason="reconfigure_successful"
            )
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return EnergySplitOptionsFlow(entry)


class EnergySplitOptionsFlow(OptionsFlow):
    """Options flow for Energy Split.

    The options flow is menu-driven. Every action mutates ``entry.options``
    and reloads the config entry via the update listener; the coordinator
    picks the new snapshot up on its next tick. Tenant *slugs* are
    intentionally immutable after creation because they anchor every
    entity's ``unique_id``; renaming changes only the display name.
    """

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._pending_rename_slug: str | None = None
        self._pending_remove_slug: str | None = None

    def _current_tenants(self) -> list[dict[str, Any]]:
        options = self.entry.options
        data = self.entry.data
        tenants = list(options.get("tenants") or data.get("tenants") or [])
        return [dict(t) for t in tenants]

    def _finalize(self, updates: dict[str, Any]) -> ConfigFlowResult:
        """Merge ``updates`` into the current options and finalise the flow.

        Home Assistant's options flow finalises via
        ``self.async_create_entry(data=X)`` which OVERWRITES the whole
        options dict, so every step must return the merged snapshot rather
        than mutating ``entry.options`` in-place.
        """
        merged = dict(self.entry.options)
        merged.update(updates)
        return self.async_create_entry(title="", data=merged)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the top-level options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_tenant",
                "rename_tenant",
                "remove_tenant",
                "freshness",
                "tariff_edit",
            ],
        )

    async def async_step_add_tenant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new tenant to the config entry."""
        errors: dict[str, str] = {}
        tenants = self._current_tenants()
        existing_slugs = {t.get("slug") for t in tenants}
        if user_input is not None:
            slug = str(user_input["slug"]).strip()
            name = str(user_input["name"]).strip()
            if not _validate_slug(slug):
                errors["slug"] = "invalid_slug"
            elif slug in existing_slugs:
                errors["slug"] = "duplicate_slug"
            if not errors:
                try:
                    AllocationPolicy(str(user_input["allocation_policy"]))
                except ValueError:
                    errors["allocation_policy"] = "invalid_policy"
            if not errors:
                tenants.append(
                    {
                        "slug": slug,
                        "name": name,
                        "allocation_policy": user_input["allocation_policy"],
                        "energy_entity": user_input.get("energy_entity"),
                        "power_entity": user_input.get("power_entity"),
                        "shared_loads": [],
                    }
                )
                return self._finalize({"tenants": tenants})
        schema = vol.Schema(
            {
                vol.Required("slug"): str,
                vol.Required("name"): str,
                vol.Required(
                    "allocation_policy",
                    default=AllocationPolicy.DIRECT_METER.value,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[p.value for p in AllocationPolicy],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("energy_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Optional("power_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="power")
                ),
            }
        )
        return self.async_show_form(step_id="add_tenant", data_schema=schema, errors=errors)

    async def async_step_rename_tenant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a tenant and update its display name."""
        tenants = self._current_tenants()
        if not tenants:
            return self.async_abort(reason="no_tenants")

        if user_input is not None and self._pending_rename_slug is None:
            self._pending_rename_slug = str(user_input["slug"])
            return await self.async_step_rename_tenant_confirm()

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
        return self.async_show_form(step_id="rename_tenant", data_schema=schema)

    async def async_step_rename_tenant_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the new display name for the previously-selected tenant."""
        assert self._pending_rename_slug is not None
        tenants = self._current_tenants()
        target = next((t for t in tenants if t["slug"] == self._pending_rename_slug), None)
        if target is None:
            self._pending_rename_slug = None
            return self.async_abort(reason="unknown_tenant")

        if user_input is not None:
            new_name = str(user_input["name"]).strip()
            if not new_name:
                return self.async_show_form(
                    step_id="rename_tenant_confirm",
                    data_schema=vol.Schema({vol.Required("name"): str}),
                    errors={"name": "invalid_name"},
                    description_placeholders={"slug": self._pending_rename_slug},
                )
            for tenant in tenants:
                if tenant["slug"] == self._pending_rename_slug:
                    tenant["name"] = new_name
                    break
            self._pending_rename_slug = None
            return self._finalize({"tenants": tenants})

        return self.async_show_form(
            step_id="rename_tenant_confirm",
            data_schema=vol.Schema(
                {vol.Required("name", default=target["name"]): str}
            ),
            description_placeholders={"slug": self._pending_rename_slug},
        )

    async def async_step_remove_tenant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a tenant and remove it. Enforces the minimum-two-tenant rule."""
        tenants = self._current_tenants()
        if len(tenants) <= _COUNT_MIN:
            return self.async_abort(reason="minimum_tenants")

        if user_input is not None:
            slug = str(user_input["slug"])
            self._pending_remove_slug = slug
            return await self.async_step_remove_tenant_confirm()

        options = [
            selector.SelectOptionDict(value=t["slug"], label=f'{t["name"]} ({t["slug"]})')
            for t in tenants
        ]
        return self.async_show_form(
            step_id="remove_tenant",
            data_schema=vol.Schema(
                {
                    vol.Required("slug"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, mode=selector.SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    async def async_step_remove_tenant_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Final confirm for the destructive remove-tenant action."""
        assert self._pending_remove_slug is not None
        tenants = self._current_tenants()
        target = next((t for t in tenants if t["slug"] == self._pending_remove_slug), None)
        if target is None:
            self._pending_remove_slug = None
            return self.async_abort(reason="unknown_tenant")

        if user_input is not None:
            if user_input.get("confirm"):
                tenants = [
                    t for t in tenants if t["slug"] != self._pending_remove_slug
                ]
                self._pending_remove_slug = None
                return self._finalize({"tenants": tenants})
            self._pending_remove_slug = None
            return self._finalize({})

        return self.async_show_form(
            step_id="remove_tenant_confirm",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={"slug": self._pending_remove_slug, "name": target["name"]},
        )

    async def async_step_freshness(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tune per-data-class freshness windows (see requirement I2)."""
        current = dict(self.entry.options.get("freshness") or self.entry.data.get("freshness") or {})
        if user_input is not None:
            return self._finalize(
                {
                    "freshness": {
                        "power_max_age_s": int(user_input["power_max_age_s"]),
                        "energy_max_age_s": int(user_input["energy_max_age_s"]),
                        "battery_ledger_max_age_s": int(user_input["battery_ledger_max_age_s"]),
                        "alignment_skew_s": int(user_input["alignment_skew_s"]),
                    }
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
                    "battery_ledger_max_age_s",
                    default=int(current.get("battery_ledger_max_age_s", 900)),
                ): vol.All(int, vol.Range(min=60, max=86400)),
                vol.Required(
                    "alignment_skew_s", default=int(current.get("alignment_skew_s", 180))
                ): vol.All(int, vol.Range(min=10, max=3600)),
            }
        )
        return self.async_show_form(step_id="freshness", data_schema=schema)

    async def async_step_tariff_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Append a new priced entry for a named tariff slot.

        Appending, rather than overwriting, preserves the accounting-epoch
        contract from requirement I9: past intervals keep their original
        rate; only intervals whose ``effective_from`` is <= their timestamp
        pick up the new rate.
        """
        known_slots = {"day", "night"}
        schedule = self.entry.options.get("tariff_schedule") or self.entry.data.get(
            "tariff_schedule"
        )
        if schedule and schedule.get("slots"):
            known_slots = {s["slot"] for s in schedule["slots"]}

        errors: dict[str, str] = {}
        if user_input is not None:
            slot = str(user_input["slot"])
            rate = float(user_input["rate"])
            if slot not in known_slots:
                errors["slot"] = "unknown_slot"
            elif rate < 0:
                errors["rate"] = "invalid_rate"
            if not errors:
                current_schedule = dict(
                    self.entry.options.get("tariff_schedule")
                    or self.entry.data.get("tariff_schedule")
                    or {}
                )
                slots_list = list(current_schedule.get("slots", []))
                slots_list.append(
                    {
                        "slot": slot,
                        "rate": rate,
                        "effective_from": datetime.now(UTC).isoformat(),
                    }
                )
                current_schedule["slots"] = slots_list
                return self._finalize({"tariff_schedule": current_schedule})

        schema = vol.Schema(
            {
                vol.Required("slot", default=next(iter(sorted(known_slots)))): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sorted(known_slots),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("rate", default=0.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step="any", mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="tariff_edit", data_schema=schema, errors=errors)


