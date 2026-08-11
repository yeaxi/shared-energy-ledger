/**
 * `energy-split-period-summary` custom card.
 *
 * Renders per-tenant known cost for the selected accounting period.
 * Two data sources are supported (only one at a time per card instance):
 *
 * 1. Cumulative-cost sensor per tenant. The sensor is provided by the
 *    integration and MUST expose the configured `expected_unit`. If the
 *    entity is missing, in an invalid state, or the unit does not match,
 *    the tenant renders as "unavailable" and the numeric value is never
 *    substituted with `0` (invariants I1, I10).
 *
 * 2. Recorder-based report JSON at `historical_data_url`. The URL is
 *    fetched same-origin, validated with `parseReport`, and the
 *    `tenants[slug].known_cost` field is displayed. A monotonic selection
 *    guard on `finalized_as_of` protects against out-of-order async
 *    responses (invariant I8).
 */

import { escapeHtml } from "./common/escape";
import { fetchJson } from "./common/fetcher";
import {
  defineCustomElementOnce,
  registerCustomCard,
} from "./common/register";
import { CARD_BASE_CSS } from "./common/theme";
import {
  isInvalidState,
  resolveLocale,
  type HassEntityState,
  type HassLike,
} from "./common/hass";
import { t } from "../i18n";
import { parseReport } from "../report/validate";
import {
  INITIAL_SELECTION,
  advanceSelection,
  shouldAcceptSelection,
  type SelectionState,
} from "../report/selection";
import type { ReportEnvelope } from "../report/schema";

export interface PeriodSummaryConfig {
  readonly type: string;
  readonly title?: string;
  readonly entities: Readonly<Record<string, string>>;
  readonly expected_unit: string;
  readonly display_unit?: string;
  readonly decimals?: number;
  readonly historical_data_url?: string;
}

const CARD_TYPE = "energy-split-period-summary";

function isValidConfig(raw: unknown): raw is PeriodSummaryConfig {
  if (typeof raw !== "object" || raw === null) {
    return false;
  }
  const cfg = raw as Record<string, unknown>;
  if (typeof cfg["expected_unit"] !== "string" || cfg["expected_unit"].length === 0) {
    return false;
  }
  const entities = cfg["entities"];
  if (typeof entities !== "object" || entities === null) {
    return false;
  }
  const entriesOk = Object.entries(entities as Record<string, unknown>).every(
    ([slug, entityId]) =>
      typeof slug === "string" &&
      slug.length > 0 &&
      typeof entityId === "string" &&
      entityId.length > 0,
  );
  if (!entriesOk) {
    return false;
  }
  if (cfg["decimals"] !== undefined) {
    const decimals = cfg["decimals"];
    if (typeof decimals !== "number" || !Number.isInteger(decimals) || decimals < 0) {
      return false;
    }
  }
  return true;
}

function formatAmount(raw: string, decimals: number): string {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) {
    return raw;
  }
  return parsed.toFixed(decimals);
}

export class EnergySplitPeriodSummary extends HTMLElement {
  private _hass: HassLike | null = null;
  private _config: PeriodSummaryConfig | null = null;
  private _report: ReportEnvelope | null = null;
  private _selection: SelectionState = INITIAL_SELECTION;
  private _fetchAbort: AbortController | null = null;
  private _reportError: string | null = null;
  private readonly _root: ShadowRoot;

  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  static getStubConfig(): PeriodSummaryConfig {
    return {
      type: `custom:${CARD_TYPE}`,
      title: t("card.period_summary.title"),
      entities: { "tenant-a": "sensor.energy_split_tenant_a_cost_cumulative" },
      expected_unit: "EUR",
      display_unit: "EUR",
      decimals: 2,
    };
  }

  getCardSize(): number {
    if (this._config === null) {
      return 1;
    }
    const rows = Object.keys(this._config.entities).length;
    return Math.max(2, Math.ceil(rows / 2));
  }

  setConfig(config: unknown): void {
    if (!isValidConfig(config)) {
      throw new Error(t("error.invalid_config"));
    }
    this._config = config;
    this._report = null;
    this._selection = INITIAL_SELECTION;
    this._reportError = null;
    if (this._fetchAbort !== null) {
      this._fetchAbort.abort();
      this._fetchAbort = null;
    }
    this._render();
    void this._maybeFetchReport();
  }

  set hass(hass: HassLike | null) {
    this._hass = hass;
    this._render();
  }

  get hass(): HassLike | null {
    return this._hass;
  }

  disconnectedCallback(): void {
    if (this._fetchAbort !== null) {
      this._fetchAbort.abort();
      this._fetchAbort = null;
    }
  }

  private async _maybeFetchReport(): Promise<void> {
    const url = this._config?.historical_data_url;
    if (typeof url !== "string" || url.length === 0) {
      return;
    }
    if (this._fetchAbort !== null) {
      this._fetchAbort.abort();
    }
    const controller = new AbortController();
    this._fetchAbort = controller;
    const raw = await fetchJson(url, { signal: controller.signal });
    if (!raw.ok) {
      this._reportError = raw.reason;
      this._report = null;
      this._render();
      return;
    }
    const parsed = await parseReport(raw.value);
    if (!parsed.ok) {
      this._reportError = parsed.reason;
      this._report = null;
      this._render();
      return;
    }
    const envelope = parsed.value;
    if (!shouldAcceptSelection(this._selection, envelope.finalized_as_of)) {
      return;
    }
    this._selection = advanceSelection(this._selection, envelope.finalized_as_of);
    this._report = envelope;
    this._reportError = null;
    this._render();
  }

  private _render(): void {
    const config = this._config;
    if (config === null) {
      this._root.innerHTML = `<style>${CARD_BASE_CSS}</style><div class="header">${t("card.period_summary.name")}</div>`;
      return;
    }
    const locale = resolveLocale(this._hass);
    const rows = this._buildRows(config, locale);
    const title = config.title ?? t("card.period_summary.title");
    const displayUnit = config.display_unit ?? config.expected_unit;
    const footerParts: string[] = [];
    if (this._report !== null) {
      footerParts.push(
        `${t("field.finalized_as_of", locale)}: ${escapeHtml(this._report.finalized_as_of)}`,
      );
      footerParts.push(
        `${t("field.currency", locale)}: ${escapeHtml(this._report.currency)}`,
      );
    } else if (this._reportError !== null && config.historical_data_url !== undefined) {
      footerParts.push(escapeHtml(t("error.invalid_report", locale)));
    }
    const html = `
      <style>${CARD_BASE_CSS}</style>
      <div class="header">${escapeHtml(title)}</div>
      <div class="grid" role="list">
        ${rows
          .map(
            (row) => `
              <div class="row" role="listitem">
                <span class="label">${escapeHtml(row.slug)}</span>
                <span class="value ${row.unavailable ? "unavailable" : ""}">${
                  row.unavailable
                    ? escapeHtml(t("state.unavailable", locale))
                    : `${escapeHtml(row.text)} ${escapeHtml(displayUnit)}`
                }</span>
              </div>`,
          )
          .join("")}
      </div>
      ${footerParts.length > 0 ? `<div class="footer">${footerParts.join(" · ")}</div>` : ""}
    `;
    this._root.innerHTML = html;
  }

  private _buildRows(
    config: PeriodSummaryConfig,
    _locale: string,
  ): Array<{ readonly slug: string; readonly text: string; readonly unavailable: boolean }> {
    const decimals = config.decimals ?? 2;
    const useReport = typeof config.historical_data_url === "string";
    return Object.entries(config.entities).map(([slug, entityId]) => {
      if (useReport) {
        if (this._report === null) {
          return { slug, text: "", unavailable: true };
        }
        const section = this._report.tenants[slug];
        if (section === undefined) {
          return { slug, text: "", unavailable: true };
        }
        return {
          slug,
          text: formatAmount(section.known_cost, decimals),
          unavailable: false,
        };
      }
      if (this._hass === null) {
        return { slug, text: "", unavailable: true };
      }
      const state: HassEntityState | undefined = this._hass.states[entityId];
      if (state === undefined) {
        return { slug, text: "", unavailable: true };
      }
      if (isInvalidState(state.state)) {
        return { slug, text: "", unavailable: true };
      }
      const unit = state.attributes.unit_of_measurement;
      if (typeof unit !== "string" || unit !== config.expected_unit) {
        return { slug, text: "", unavailable: true };
      }
      const numeric = Number(state.state);
      if (!Number.isFinite(numeric) || numeric < 0) {
        return { slug, text: "", unavailable: true };
      }
      return {
        slug,
        text: numeric.toFixed(decimals),
        unavailable: false,
      };
    });
  }
}

defineCustomElementOnce(CARD_TYPE, EnergySplitPeriodSummary);
registerCustomCard({
  type: CARD_TYPE,
  name: t("card.period_summary.name"),
  description: t("card.period_summary.description"),
  preview: false,
});
