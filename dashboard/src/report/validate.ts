/**
 * Pure `parseReport` function used by every card that consumes report JSON.
 *
 * The parser fails closed: any structural, type, or numeric anomaly returns
 * a `Result` with `ok: false`. Callers MUST render "unavailable" in that
 * case (REQUIREMENTS.md invariants I1, I7, I10). The parser never fabricates
 * a `0` for a missing or wrong-typed field.
 *
 * Verification of the report revision hash uses `sha256Hex` from
 * `./canonical`, which prefers WebCrypto and falls back to a small
 * self-contained SHA-256 implementation.
 */

import {
  REPORT_SCHEMA_VERSION,
  err,
  ok,
  type HourSource,
  type HourlyRow,
  type ReportEnvelope,
  type ReportPeriod,
  type Result,
  type TenantSection,
} from "./schema";
import {
  CanonicalError,
  canonicalStringify,
  sha256Hex,
  type CanonicalValue,
} from "./canonical";

const REVISION_HEX_RE = /^[0-9a-f]{64}$/;
const ISO_UTC_RE = /Z$/;
const DECIMAL_RE = /^-?\d+(?:\.\d+)?$/;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Number.isInteger(value) &&
    value >= 0
  );
}

function isNonNegativeFiniteNumber(value: unknown): value is number {
  return isFiniteNumber(value) && value >= 0;
}

function isDecimalString(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }
  if (!DECIMAL_RE.test(value)) {
    return false;
  }
  return !value.startsWith("-");
}

function parsePeriod(raw: unknown): Result<ReportPeriod> {
  if (!isPlainObject(raw)) {
    return err("period must be an object");
  }
  const fields: (keyof ReportPeriod)[] = [
    "start_local",
    "end_local",
    "start_utc",
    "end_utc",
  ];
  for (const field of fields) {
    const value = raw[field];
    if (typeof value !== "string" || value.length === 0) {
      return err(`period.${field} must be a non-empty string`);
    }
  }
  const startUtc = raw["start_utc"] as string;
  const endUtc = raw["end_utc"] as string;
  if (!ISO_UTC_RE.test(startUtc) || !ISO_UTC_RE.test(endUtc)) {
    return err("period.*_utc must end in 'Z'");
  }
  return ok({
    start_local: raw["start_local"] as string,
    end_local: raw["end_local"] as string,
    start_utc: startUtc,
    end_utc: endUtc,
  });
}

function parseHourlyRow(raw: unknown, index: number, slug: string): Result<HourlyRow> {
  if (!isPlainObject(raw)) {
    return err(`tenants.${slug}.hourly[${index}] must be an object`);
  }
  const hourLocal = raw["hour_local"];
  if (typeof hourLocal !== "string" || hourLocal.length === 0) {
    return err(`tenants.${slug}.hourly[${index}].hour_local must be a string`);
  }
  const cost = raw["cost"];
  if (!isDecimalString(cost)) {
    return err(
      `tenants.${slug}.hourly[${index}].cost must be a non-negative decimal string`,
    );
  }
  const coverage = raw["coverage_seconds"];
  if (!isNonNegativeInteger(coverage) || coverage > 3600) {
    return err(
      `tenants.${slug}.hourly[${index}].coverage_seconds must be in [0, 3600]`,
    );
  }
  const source = raw["source"];
  if (source !== "direct" && source !== "derived") {
    return err(
      `tenants.${slug}.hourly[${index}].source must be 'direct' or 'derived'`,
    );
  }
  return ok({
    hour_local: hourLocal,
    cost,
    coverage_seconds: coverage,
    source: source as HourSource,
  });
}

function parseTenantSection(raw: unknown, slug: string): Result<TenantSection> {
  if (!isPlainObject(raw)) {
    return err(`tenants.${slug} must be an object`);
  }
  const knownCost = raw["known_cost"];
  if (!isDecimalString(knownCost)) {
    return err(`tenants.${slug}.known_cost must be a non-negative decimal string`);
  }
  const coverage = raw["coverage_seconds"];
  if (!isNonNegativeInteger(coverage)) {
    return err(`tenants.${slug}.coverage_seconds must be a non-negative integer`);
  }
  const hourly = raw["hourly"];
  if (!Array.isArray(hourly)) {
    return err(`tenants.${slug}.hourly must be an array`);
  }
  const rows: HourlyRow[] = [];
  for (let i = 0; i < hourly.length; i++) {
    const rowResult = parseHourlyRow(hourly[i], i, slug);
    if (!rowResult.ok) {
      return err(rowResult.reason);
    }
    rows.push(rowResult.value);
  }
  return ok({
    known_cost: knownCost,
    coverage_seconds: coverage,
    hourly: rows,
  });
}

function parseTenants(
  raw: unknown,
): Result<Readonly<Record<string, TenantSection>>> {
  if (!isPlainObject(raw)) {
    return err("tenants must be an object keyed by slug");
  }
  const out: Record<string, TenantSection> = {};
  for (const slug of Object.keys(raw)) {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(slug)) {
      return err(`tenants key '${slug}' is not a valid slug`);
    }
    const sectionResult = parseTenantSection(raw[slug], slug);
    if (!sectionResult.ok) {
      return err(sectionResult.reason);
    }
    out[slug] = sectionResult.value;
  }
  return ok(out);
}

function structuralParse(raw: unknown): Result<ReportEnvelope> {
  if (!isPlainObject(raw)) {
    return err("Report must be a JSON object");
  }
  const schemaVersion = raw["schema_version"];
  if (schemaVersion !== REPORT_SCHEMA_VERSION) {
    return err(
      `schema_version must equal ${REPORT_SCHEMA_VERSION}, got ${String(schemaVersion)}`,
    );
  }
  const revision = raw["revision"];
  if (typeof revision !== "string" || !REVISION_HEX_RE.test(revision)) {
    return err("revision must be a 64-character lowercase hex string");
  }
  const finalizedAsOf = raw["finalized_as_of"];
  if (typeof finalizedAsOf !== "string" || !ISO_UTC_RE.test(finalizedAsOf)) {
    return err("finalized_as_of must be an ISO-8601 UTC string ending in 'Z'");
  }
  const timezone = raw["timezone"];
  if (typeof timezone !== "string" || timezone.length === 0) {
    return err("timezone must be a non-empty IANA name");
  }
  const currency = raw["currency"];
  if (typeof currency !== "string" || !/^[A-Z]{3}$/.test(currency)) {
    return err("currency must be an ISO 4217 3-letter code");
  }
  const periodResult = parsePeriod(raw["period"]);
  if (!periodResult.ok) {
    return err(periodResult.reason);
  }
  const coverage = raw["coverage_seconds"];
  if (!isNonNegativeInteger(coverage)) {
    return err("coverage_seconds must be a non-negative integer");
  }
  const transitionExcluded = raw["transition_excluded_seconds"];
  if (!isNonNegativeInteger(transitionExcluded)) {
    return err("transition_excluded_seconds must be a non-negative integer");
  }
  const unpricedBattery = raw["unpriced_battery_kwh"];
  if (!isNonNegativeFiniteNumber(unpricedBattery)) {
    return err("unpriced_battery_kwh must be a non-negative finite number");
  }
  const tenantsResult = parseTenants(raw["tenants"]);
  if (!tenantsResult.ok) {
    return err(tenantsResult.reason);
  }
  return ok({
    schema_version: REPORT_SCHEMA_VERSION,
    revision,
    finalized_as_of: finalizedAsOf,
    timezone,
    currency,
    period: periodResult.value,
    coverage_seconds: coverage,
    transition_excluded_seconds: transitionExcluded,
    unpriced_battery_kwh: unpricedBattery,
    tenants: tenantsResult.value,
  });
}

/**
 * Build the canonical body used for revision computation. The `revision`
 * field is stripped exactly as the Python side does.
 */
export function canonicalBody(envelope: ReportEnvelope): CanonicalValue {
  const clone: Record<string, CanonicalValue> = {
    schema_version: envelope.schema_version,
    finalized_as_of: envelope.finalized_as_of,
    timezone: envelope.timezone,
    currency: envelope.currency,
    period: {
      start_local: envelope.period.start_local,
      end_local: envelope.period.end_local,
      start_utc: envelope.period.start_utc,
      end_utc: envelope.period.end_utc,
    },
    coverage_seconds: envelope.coverage_seconds,
    transition_excluded_seconds: envelope.transition_excluded_seconds,
    unpriced_battery_kwh: envelope.unpriced_battery_kwh,
    tenants: Object.fromEntries(
      Object.entries(envelope.tenants).map(([slug, section]) => [
        slug,
        {
          known_cost: section.known_cost,
          coverage_seconds: section.coverage_seconds,
          hourly: section.hourly.map((row) => ({
            hour_local: row.hour_local,
            cost: row.cost,
            coverage_seconds: row.coverage_seconds,
            source: row.source,
          })),
        },
      ]),
    ),
  };
  return clone;
}

/**
 * Public entry point. Consumes an untyped value (for example
 * `await fetch(url).then((r) => r.json())`) and returns a `Result`.
 *
 * When `ok: false`, the caller MUST render the fail-closed "unavailable"
 * state; the returned `reason` is intended for developer diagnostics only
 * and MUST NOT be shown to end users verbatim.
 */
export async function parseReport(input: unknown): Promise<Result<ReportEnvelope>> {
  if (input instanceof Error) {
    return err(input.message);
  }
  if (input === null || input === undefined) {
    return err("Report body is missing");
  }
  if (containsNonFiniteNumber(input)) {
    return err("Report contains a NaN or Infinity value");
  }
  const structural = structuralParse(input);
  if (!structural.ok) {
    return structural;
  }
  const envelope = structural.value;
  let canonical: string;
  try {
    canonical = canonicalStringify(canonicalBody(envelope));
  } catch (e) {
    if (e instanceof CanonicalError) {
      return err(e.message);
    }
    return err("Unexpected error while canonicalising report");
  }
  const computed = await sha256Hex(canonical);
  if (computed !== envelope.revision) {
    return err(
      `revision mismatch: expected ${envelope.revision}, computed ${computed}`,
    );
  }
  return ok(envelope);
}

function containsNonFiniteNumber(value: unknown): boolean {
  if (typeof value === "number") {
    return !Number.isFinite(value);
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      if (containsNonFiniteNumber(item)) {
        return true;
      }
    }
    return false;
  }
  if (isPlainObject(value)) {
    for (const key of Object.keys(value)) {
      if (containsNonFiniteNumber(value[key])) {
        return true;
      }
    }
    return false;
  }
  return false;
}
