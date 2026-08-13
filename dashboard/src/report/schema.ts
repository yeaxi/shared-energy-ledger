/**
 * TypeScript surface for the v3 report envelope produced by
 * `custom_components/shared_energy_ledger/report.py`.
 *
 * These types are the smallest shape the card needs. They MUST stay in
 * lock-step with the Python report builder; see REQUIREMENTS.md invariant I7.
 * Any field marked required here is a hard requirement for the card, and its
 * absence forces the card into the fail-closed "unavailable" state (I10).
 *
 * Currency and kWh amounts are decimal strings (not JSON floats) so the
 * canonical revision hash is identical in Python and JavaScript.
 */

export const REPORT_SCHEMA_VERSION = 3 as const;

export interface HourlyRow {
  readonly hour_local: string;
  readonly cost: string;
  readonly grid_cost: string;
  readonly pv_cost: string;
  readonly battery_cost: string;
  readonly coverage_seconds: number;
}

export interface TenantSection {
  readonly known_cost: string;
  readonly grid_cost: string;
  readonly pv_cost: string;
  readonly battery_cost: string;
  readonly coverage_seconds: number;
  readonly hourly: readonly HourlyRow[];
}

export interface ReportPeriod {
  readonly start_local: string;
  readonly end_local: string;
  readonly start_utc: string;
  readonly end_utc: string;
}

export interface ReportEnvelope {
  readonly schema_version: typeof REPORT_SCHEMA_VERSION;
  readonly revision: string;
  readonly finalized_as_of: string;
  readonly timezone: string;
  readonly currency: string;
  readonly period: ReportPeriod;
  readonly coverage_seconds: number;
  readonly transition_excluded_seconds: number;
  readonly unavailable_seconds: number;
  readonly unpriced_battery_kwh: string;
  readonly reconciliation_kwh: string | null;
  readonly tenants: Readonly<Record<string, TenantSection>>;
}

/**
 * A conservative Result discriminated union used by the report parser and by
 * the card. Nothing outside this module throws for validation errors; callers
 * pattern-match on `ok` and fall back to `unavailable` when `ok` is `false`.
 */
export type Result<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly reason: string };

export function ok<T>(value: T): Result<T> {
  return { ok: true, value };
}

export function err<T = never>(reason: string): Result<T> {
  return { ok: false, reason };
}
