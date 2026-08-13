/**
 * Tiny translation dictionary. English is the baseline (see
 * `dashboard/AGENTS.md`, "Every user-visible string is localized"). Other
 * locales are scaffolded and fall back to English when a key is missing.
 *
 * Keys are prefixed by feature area (`card.`, `state.`, ...). Interpolation
 * uses `{name}` placeholders substituted at call time.
 */

const EN = {
  "state.unavailable": "unavailable",
  "state.loading": "Loading",
  "state.no_data": "No data for this period",
  "card.report.title": "Who owes how much",
  "card.report.name": "Shared Energy Ledger report",
  "card.report.description":
    "Per-tenant cost for any period, split by grid, PV, and battery, computed by the integration service.",
  "column.tenant": "Tenant",
  "column.total": "Total",
  "column.grid": "Grid",
  "column.pv": "PV",
  "column.battery": "Battery",
  "field.coverage_seconds": "Coverage (s)",
  "field.transition_excluded_seconds": "Transition-excluded (s)",
  "field.unavailable_seconds": "Unavailable (s)",
  "field.unpriced_battery_kwh": "Unpriced battery (kWh)",
  "field.reconciliation_kwh": "Reconciliation (kWh)",
  "field.finalized_as_of": "Finalized as of",
  "field.timezone": "Timezone",
  "field.currency": "Currency",
  "field.known_cost": "Known cost",
  "error.invalid_config": "Card configuration is invalid.",
  "error.invalid_report": "Report failed validation and cannot be shown.",
  "error.stale_report": "A newer selection is already displayed.",
  "error.network": "Could not run the report service.",
  "error.unit_mismatch": "Sensor unit does not match the expected unit.",
} as const;

export type TranslationKey = keyof typeof EN;

const DICTIONARIES: Readonly<Record<string, Partial<Record<TranslationKey, string>>>> = {
  en: EN,
};

/**
 * Translate `key` using the requested locale, falling back to English.
 *
 * @param key one of the well-known translation keys.
 * @param locale BCP-47 code; only the primary subtag is inspected.
 * @param vars named placeholder values referenced as `{name}` in the string.
 */
export function t(
  key: TranslationKey,
  locale?: string,
  vars?: Readonly<Record<string, string | number>>,
): string {
  const primary = (locale ?? "en").split("-")[0]?.toLowerCase() ?? "en";
  const localized = DICTIONARIES[primary]?.[key];
  const fallback = EN[key];
  const template = localized ?? fallback;
  if (vars === undefined) {
    return template;
  }
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name: string) => {
    const value = vars[name];
    return value === undefined ? match : String(value);
  });
}

export const AVAILABLE_LOCALES: readonly string[] = Object.keys(DICTIONARIES);
