---
name: ha-coordinator-and-entities
description: Structure a DataUpdateCoordinator, model entities with EntityDescriptions, and keep unique_ids, availability, and RestoreEntity behavior correct for a Home Assistant custom integration. Use when creating or refactoring coordinator.py, sensor.py, or binary_sensor.py.
---

# HA coordinator and entities

`DataUpdateCoordinator` is the standard state hub for a Home Assistant custom
integration. This skill defines the coordinator/entity contract that Platinum
integrations follow and that most Silver and Gold integrations should follow
too.

## Trigger

Invoke this skill when:

- Creating a new coordinator or a new entity platform.
- Refactoring entity state to move fetches out of `async_update`.
- Adding a cumulative-total sensor that must survive Home Assistant restarts.
- Auditing `unique_id` stability during a schema migration.

## Preconditions

- The integration has a `ConfigEntry` and a working config flow.
- The upstream data source is either pollable, subscribable, or push-based.
- Type stubs for the coordinator payload live in `models.py`.

## Coordinator shape

- Subclass `DataUpdateCoordinator[<PayloadType>]`. The payload is a typed
  dataclass or `TypedDict`, never a bare `dict`.
- Store the coordinator on `entry.runtime_data`. Do not use
  `hass.data[DOMAIN][entry.entry_id]` as the primary store.
- `_async_update_data` performs a single pass over all inputs. Individual
  fields report unavailability via a sentinel or `None`; the coordinator does
  not fabricate zeros.
- Configure `update_interval` and, where applicable,
  `always_update=False` so entities do not re-emit unchanged states.
- Register a listener via `entry.async_on_unload` for the options-update
  listener; the coordinator reloads cleanly when options change.

## Entity descriptions

- Every platform defines a frozen dataclass extending
  `SensorEntityDescription`, `BinarySensorEntityDescription`,
  `NumberEntityDescription`, or `SelectEntityDescription`.
- Each description carries: `key`, `translation_key`, `device_class` (when
  applicable), `state_class` (for sensors), `native_unit_of_measurement`,
  `icon`, and a `value_fn` that maps coordinator data to a state.
- Entities extend `CoordinatorEntity[<CoordinatorType>]` and set
  `_attr_has_entity_name = True`. Entity `name` is derived from
  `translation_key`, not hard-coded strings.

## Unique-id policy

- `unique_id` combines `config_entry.entry_id` with a stable per-resource slug
  and the description `key`. Example:
  `f"{entry.entry_id}:{tenant_slug}:{description.key}"`.
- Renaming a tenant or resource slug goes through a documented migration path;
  the raw `entry_id` never appears on its own except for singleton entities.
- Never use user-supplied display names as part of `unique_id`.

## Availability propagation

- `available` returns `self.coordinator.last_update_success and value is not None`
  where `value` is the mapped state.
- Where an entity depends on a distinct freshness gate (e.g., grid, PV,
  battery), the entity's `available` also checks that gate. The gate itself is
  a binary sensor exposed by the same coordinator.
- An entity is never `unknown` when its dependencies are down; it is
  `unavailable`.

## RestoreEntity for cumulative totals

- Cumulative-total sensors (monetary totals, utility-meter helpers) inherit
  from `RestoreSensor` (or `RestoreEntity` for non-sensor platforms).
- `async_added_to_hass` restores the last valid state and unit. If unit
  changed (e.g., currency change), the restore is discarded and the sensor
  starts a new accounting epoch, journaled in `attributes.accounting_epoch`.
- Restored states are validated against the invariants in
  `energy-accounting-invariants` before being trusted.

## Device registry

- Register a single device per config entry via
  `DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=<title>)`.
- Sub-resources (e.g., tenants) may register additional devices with
  `via_device=(DOMAIN, entry.entry_id)` and their own stable identifiers.

## Forbidden patterns

- Entities that call remote APIs from their own `async_update`.
- Entity classes with more than one `async_setup_entry`-registered callback
  path; one `async_setup_entry` per platform.
- `_attr_name` set to a raw string instead of using `translation_key`.
- Cumulative sensors without `RestoreSensor`.
- Coordinators returning `dict[str, Any]`; payloads must be typed.
- Any use of `time.sleep`, `asyncio.sleep(...)` inside an entity property.

## Verification

- `pytest tests/test_entities.py -q` covers every platform's state, unit,
  device class, unique_id, and availability paths.
- `mypy --strict` reports zero errors on the coordinator and entity modules.
- A restart-simulation test confirms that cumulative totals survive across
  `pytest-homeassistant-custom-component`'s `hass` fixture restart.
