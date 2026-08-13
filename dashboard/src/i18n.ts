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
  "card.period_summary.title": "Energy split - period summary",
  "card.period_summary.name": "Shared Energy Ledger period summary",
  "card.period_summary.description":
    "Per-tenant known cost for a selected period.",
  "card.history_report.title": "Energy split - history report",
  "card.history_report.name": "Shared Energy Ledger history report",
  "card.history_report.description":
    "Recorder-backed period report with coverage and transition-excluded seconds.",
  "card.history_bridge.name": "Shared Energy Ledger history bridge",
  "card.history_bridge.description":
    "Invisible data adapter that publishes the currently selected report to sibling cards.",
  "field.coverage_seconds": "Coverage (s)",
  "field.transition_excluded_seconds": "Transition-excluded (s)",
  "field.unpriced_battery_kwh": "Unpriced battery (kWh)",
  "field.finalized_as_of": "Finalized as of",
  "field.timezone": "Timezone",
  "field.currency": "Currency",
  "field.known_cost": "Known cost",
  "error.invalid_config": "Card configuration is invalid.",
  "error.invalid_report": "Report failed validation and cannot be shown.",
  "error.stale_report": "A newer selection is already displayed.",
  "error.network": "Could not fetch report from the Home Assistant frontend.",
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
