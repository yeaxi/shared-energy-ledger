/**
 * TypeScript surface for the v2 report envelope produced by
 * `custom_components/shared_energy_ledger/report.py`.
 *
 * These types are intentionally the smallest shape the cards need. They MUST
 * stay in lock-step with the Python report builder; see REQUIREMENTS.md
 * invariant I7 ("Report v2 contract"). Any field marked required here is a
 * hard requirement for the cards, and its absence forces the card into the
 * fail-closed "unavailable" state (invariant I10).
 */

export const REPORT_SCHEMA_VERSION = 2 as const;

export type HourSource = "direct" | "derived";

export interface HourlyRow {
  readonly hour_local: string;
  readonly cost: string;
  readonly coverage_seconds: number;
  readonly source: HourSource;
}

export interface TenantSection {
  readonly known_cost: string;
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
  readonly unpriced_battery_kwh: number;
  readonly tenants: Readonly<Record<string, TenantSection>>;
}

/**
 * A conservative Result discriminated union used by the report parser and by
 * the cards. Nothing outside this module should throw for validation errors;
 * callers pattern-match on `ok` and fall back to `unavailable` when `ok` is
 * `false`.
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
