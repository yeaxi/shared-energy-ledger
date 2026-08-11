/**
 * `energy-split-history-report` custom card.
 *
 * Fetches a period report JSON from the Home Assistant frontend origin,
 * validates it via `parseReport`, and renders a compact daily summary:
 * coverage seconds, transition-excluded seconds, unpriced battery kWh, and
 * per-tenant known cost.
 *
 * REQUIREMENTS.md invariants enforced here:
 * - I1/I10: fail-closed "unavailable" rendering when the report is missing,
 *   malformed, or its revision hash does not match.
 * - I7: consumes the v2 envelope exactly as produced by
 *   `custom_components/energy_split/report.py`.
 * - I8: monotonic selection guard on `finalized_as_of` discards older
 *   responses that arrive after a newer selection is already displayed.
 */

import { escapeHtml } from "./common/escape";
import { fetchJson } from "./common/fetcher";
import {
  defineCustomElementOnce,
  registerCustomCard,
} from "./common/register";
import { CARD_BASE_CSS } from "./common/theme";
import { resolveLocale, type HassLike } from "./common/hass";
import { t } from "../i18n";
import { parseReport } from "../report/validate";
import {
  INITIAL_SELECTION,
  advanceSelection,
  shouldAcceptSelection,
  type SelectionState,
} from "../report/selection";
import type { ReportEnvelope } from "../report/schema";

export interface HistoryReportConfig {
  readonly type: string;
  readonly title?: string;
  readonly url: string;
  readonly poll_interval_seconds?: number;
}

const CARD_TYPE = "energy-split-history-report";
const DEFAULT_POLL_SECONDS = 300;

function isValidConfig(raw: unknown): raw is HistoryReportConfig {
  if (typeof raw !== "object" || raw === null) {
    return false;
  }
  const cfg = raw as Record<string, unknown>;
  if (typeof cfg["url"] !== "string" || cfg["url"].length === 0) {
    return false;
  }
  if (cfg["poll_interval_seconds"] !== undefined) {
    const poll = cfg["poll_interval_seconds"];
    if (typeof poll !== "number" || !Number.isFinite(poll) || poll <= 0) {
      return false;
    }
  }
  return true;
}

export class EnergySplitHistoryReport extends HTMLElement {
  private _hass: HassLike | null = null;
  private _config: HistoryReportConfig | null = null;
  private _report: ReportEnvelope | null = null;
  private _selection: SelectionState = INITIAL_SELECTION;
  private _reportError: string | null = null;
  private _fetchAbort: AbortController | null = null;
  private _pollTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly _root: ShadowRoot;

  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  static getStubConfig(): HistoryReportConfig {
    return {
      type: `custom:${CARD_TYPE}`,
      title: t("card.history_report.title"),
      url: "/local/energy_split/report.json",
      poll_interval_seconds: DEFAULT_POLL_SECONDS,
    };
  }

  getCardSize(): number {
    return 4;
  }

  setConfig(config: unknown): void {
    if (!isValidConfig(config)) {
      throw new Error(t("error.invalid_config"));
    }
    this._config = config;
    this._report = null;
    this._selection = INITIAL_SELECTION;
    this._reportError = null;
    this._render();
    void this._fetchOnce();
    this._schedulePoll();
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
    if (this._pollTimer !== null) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
  }

  private _schedulePoll(): void {
    if (this._pollTimer !== null) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
    const interval = this._config?.poll_interval_seconds ?? DEFAULT_POLL_SECONDS;
    this._pollTimer = setTimeout(() => {
      void this._fetchOnce().then(() => this._schedulePoll());
    }, interval * 1000);
  }

  private async _fetchOnce(): Promise<void> {
    const config = this._config;
    if (config === null) {
      return;
    }
    if (this._fetchAbort !== null) {
      this._fetchAbort.abort();
    }
    const controller = new AbortController();
    this._fetchAbort = controller;
    const raw = await fetchJson(config.url, { signal: controller.signal });
    if (!raw.ok) {
      this._reportError = raw.reason;
      this._render();
      return;
    }
    const parsed = await parseReport(raw.value);
    if (!parsed.ok) {
      this._reportError = parsed.reason;
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
    const locale = resolveLocale(this._hass);
    if (config === null) {
      this._root.innerHTML = `<style>${CARD_BASE_CSS}</style><div class="header">${escapeHtml(
        t("card.history_report.name", locale),
      )}</div>`;
      return;
    }
    const title = config.title ?? t("card.history_report.title", locale);
    if (this._report === null) {
      const message =
        this._reportError === null
          ? t("state.loading", locale)
          : t("error.invalid_report", locale);
      this._root.innerHTML = `
        <style>${CARD_BASE_CSS}</style>
        <div class="header">${escapeHtml(title)}</div>
        <div class="row">
          <span class="label">${escapeHtml(t("field.finalized_as_of", locale))}</span>
          <span class="value unavailable">${escapeHtml(t("state.unavailable", locale))}</span>
        </div>
        <div class="footer">${escapeHtml(message)}</div>
      `;
      return;
    }
    const envelope = this._report;
    const tenantRows = Object.entries(envelope.tenants)
      .map(
        ([slug, section]) => `
          <div class="row">
            <span class="label">${escapeHtml(slug)}</span>
            <span class="value">${escapeHtml(section.known_cost)} ${escapeHtml(envelope.currency)}</span>
          </div>`,
      )
      .join("");
    this._root.innerHTML = `
      <style>${CARD_BASE_CSS}</style>
      <div class="header">${escapeHtml(title)}</div>
      <div class="subtitle">${escapeHtml(envelope.period.start_local)} → ${escapeHtml(envelope.period.end_local)}</div>
      <div class="grid">
        <div class="row">
          <span class="label">${escapeHtml(t("field.coverage_seconds", locale))}</span>
          <span class="value">${envelope.coverage_seconds}</span>
        </div>
        <div class="row">
          <span class="label">${escapeHtml(t("field.transition_excluded_seconds", locale))}</span>
          <span class="value">${envelope.transition_excluded_seconds}</span>
        </div>
        <div class="row">
          <span class="label">${escapeHtml(t("field.unpriced_battery_kwh", locale))}</span>
          <span class="value">${envelope.unpriced_battery_kwh}</span>
        </div>
      </div>
      <div class="header" style="margin-top:12px;">${escapeHtml(t("field.known_cost", locale))}</div>
      <div class="grid">${tenantRows}</div>
      <div class="footer">${escapeHtml(t("field.finalized_as_of", locale))}: ${escapeHtml(envelope.finalized_as_of)}</div>
    `;
  }
}

defineCustomElementOnce(CARD_TYPE, EnergySplitHistoryReport);
registerCustomCard({
  type: CARD_TYPE,
  name: t("card.history_report.name"),
  description: t("card.history_report.description"),
  preview: false,
});
