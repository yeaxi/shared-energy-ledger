/**
 * `shared-energy-ledger-report` custom card.
 *
 * Answers "who owes how much" for a period by calling the integration's
 * `shared_energy_ledger.rebuild_period_report` service directly over the Home
 * Assistant connection and rendering the per-tenant, per-source result. There
 * is no static report file and no cross-origin fetch: the card asks the
 * integration and the integration recomputes from the meters.
 *
 * Fail-closed (invariants I1, I8, I10): the response is validated with
 * `parseReport`; anything malformed renders "unavailable". A local monotonic
 * request id guards against a slow earlier response overwriting a newer one.
 */

import { escapeHtml } from "./common/escape";
import { defineCustomElementOnce, registerCustomCard } from "./common/register";
import { CARD_BASE_CSS } from "./common/theme";
import { resolveLocale, type HassLike } from "./common/hass";
import { t } from "../i18n";
import { parseReport } from "../report/validate";
import type { ReportEnvelope } from "../report/schema";

const CARD_TYPE = "shared-energy-ledger-report";
const DOMAIN = "shared_energy_ledger";
const SERVICE = "rebuild_period_report";

export interface ReportCardConfig {
  readonly type: string;
  readonly title?: string;
  readonly period?: "today" | "this_month" | "this_year";
  readonly start?: string;
  readonly end?: string;
  readonly tenant?: string;
}

function isValidConfig(raw: unknown): raw is ReportCardConfig {
  if (typeof raw !== "object" || raw === null) {
    return false;
  }
  const cfg = raw as Record<string, unknown>;
  if (cfg["period"] !== undefined && !["today", "this_month", "this_year"].includes(String(cfg["period"]))) {
    return false;
  }
  for (const key of ["start", "end", "tenant", "title"]) {
    if (cfg[key] !== undefined && typeof cfg[key] !== "string") {
      return false;
    }
  }
  return true;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function localIso(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

function computePeriod(config: ReportCardConfig): { start: string; end: string } {
  if (typeof config.start === "string" && typeof config.end === "string") {
    return { start: config.start, end: config.end };
  }
  const now = new Date();
  const kind = config.period ?? "this_month";
  if (kind === "today") {
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    return { start: localIso(start), end: localIso(end) };
  }
  if (kind === "this_year") {
    const start = new Date(now.getFullYear(), 0, 1);
    const end = new Date(now.getFullYear() + 1, 0, 1);
    return { start: localIso(start), end: localIso(end) };
  }
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  return { start: localIso(start), end: localIso(end) };
}

export class SharedEnergyLedgerReportCard extends HTMLElement {
  private _hass: HassLike | null = null;
  private _config: ReportCardConfig | null = null;
  private _report: ReportEnvelope | null = null;
  private _error: string | null = null;
  private _loading = false;
  private _requestId = 0;
  private _acceptedRequestId = 0;
  private _loadedPeriodKey: string | null = null;
  private readonly _root: ShadowRoot;

  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  static getStubConfig(): ReportCardConfig {
    return { type: `custom:${CARD_TYPE}`, period: "this_month" };
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
    this._error = null;
    this._loadedPeriodKey = null;
    this._render();
    void this._maybeLoad();
  }

  set hass(hass: HassLike | null) {
    this._hass = hass;
    void this._maybeLoad();
  }

  get hass(): HassLike | null {
    return this._hass;
  }

  private async _maybeLoad(): Promise<void> {
    const config = this._config;
    const hass = this._hass;
    if (config === null || hass === null || typeof hass.callService !== "function") {
      return;
    }
    const { start, end } = computePeriod(config);
    const periodKey = `${start}|${end}|${config.tenant ?? ""}`;
    if (periodKey === this._loadedPeriodKey) {
      return;
    }
    this._loadedPeriodKey = periodKey;
    this._loading = true;
    this._error = null;
    this._render();

    const requestId = ++this._requestId;
    const serviceData: Record<string, unknown> = { start, end };
    if (typeof config.tenant === "string" && config.tenant.length > 0) {
      serviceData["tenant"] = config.tenant;
    }
    let response: unknown;
    try {
      const result = await hass.callService(DOMAIN, SERVICE, serviceData, undefined, false, true);
      response = result.response;
    } catch {
      if (requestId >= this._acceptedRequestId) {
        this._acceptedRequestId = requestId;
        this._loading = false;
        this._error = t("error.network");
        this._render();
      }
      return;
    }

    const parsed = await parseReport(response);
    // Monotonic request-id guard (invariant I8): ignore a stale response.
    if (requestId < this._acceptedRequestId) {
      return;
    }
    this._acceptedRequestId = requestId;
    this._loading = false;
    if (!parsed.ok) {
      this._report = null;
      this._error = t("error.invalid_report");
      this._render();
      return;
    }
    this._report = parsed.value;
    this._error = null;
    this._render();
  }

  private _render(): void {
    const config = this._config;
    const locale = resolveLocale(this._hass);
    const title = config?.title ?? t("card.report.title", locale);
    let bodyHtml: string;
    if (this._loading && this._report === null) {
      bodyHtml = `<div class="row"><span class="label">${escapeHtml(t("state.loading", locale))}</span></div>`;
    } else if (this._error !== null && this._report === null) {
      bodyHtml = `<div class="row"><span class="value unavailable">${escapeHtml(this._error)}</span></div>`;
    } else if (this._report === null) {
      bodyHtml = `<div class="row"><span class="label">${escapeHtml(t("state.no_data", locale))}</span></div>`;
    } else {
      bodyHtml = this._renderReport(this._report, locale);
    }
    this._root.innerHTML = `<style>${CARD_BASE_CSS}</style><div class="header">${escapeHtml(title)}</div>${bodyHtml}`;
  }

  private _renderReport(report: ReportEnvelope, locale: string): string {
    const currency = escapeHtml(report.currency);
    const header = `
      <div class="row heading" role="row">
        <span class="label">${escapeHtml(t("column.tenant", locale))}</span>
        <span class="value">${escapeHtml(t("column.total", locale))} (${currency})</span>
        <span class="value">${escapeHtml(t("column.grid", locale))}</span>
        <span class="value">${escapeHtml(t("column.pv", locale))}</span>
        <span class="value">${escapeHtml(t("column.battery", locale))}</span>
      </div>`;
    const rows = Object.entries(report.tenants)
      .map(
        ([slug, section]) => `
        <div class="row" role="row">
          <span class="label">${escapeHtml(slug)}</span>
          <span class="value">${escapeHtml(section.known_cost)}</span>
          <span class="value">${escapeHtml(section.grid_cost)}</span>
          <span class="value">${escapeHtml(section.pv_cost)}</span>
          <span class="value">${escapeHtml(section.battery_cost)}</span>
        </div>`,
      )
      .join("");
    const footer = [
      `${t("field.finalized_as_of", locale)}: ${escapeHtml(report.finalized_as_of)}`,
      `${t("field.coverage_seconds", locale)}: ${report.coverage_seconds}`,
      `${t("field.unavailable_seconds", locale)}: ${report.unavailable_seconds}`,
      `${t("field.unpriced_battery_kwh", locale)}: ${escapeHtml(report.unpriced_battery_kwh)}`,
      `${t("field.reconciliation_kwh", locale)}: ${escapeHtml(report.reconciliation_kwh ?? "-")}`,
    ].join(" · ");
    return `<div class="grid" role="table">${header}${rows}</div><div class="footer">${footer}</div>`;
  }
}

defineCustomElementOnce(CARD_TYPE, SharedEnergyLedgerReportCard);
registerCustomCard({
  type: CARD_TYPE,
  name: t("card.report.name"),
  description: t("card.report.description"),
  preview: false,
});
