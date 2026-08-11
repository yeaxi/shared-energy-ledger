/**
 * `energy-split-history-bridge` custom card.
 *
 * The bridge is an invisible data adapter. It fetches a validated report
 * on a schedule and publishes it to sibling cards through two channels:
 *
 * 1. A `CustomEvent` named `energy-split-report` that bubbles through the
 *    DOM. Sibling cards can listen with `addEventListener` on any common
 *    ancestor.
 * 2. A global registry `window.__energySplitReports` keyed by the bridge's
 *    `id` config. Sibling cards read the registry synchronously on render.
 *
 * The bridge itself never renders numbers; it exposes a small status line
 * so an operator placing the card on a Lovelace view can confirm that the
 * pipeline is alive. All I8/I10 fail-closed semantics apply: stale or
 * malformed reports never overwrite the current selection.
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

export interface HistoryBridgeConfig {
  readonly type: string;
  readonly id: string;
  readonly url: string;
  readonly poll_interval_seconds?: number;
}

interface BridgeRegistryEntry {
  readonly report: ReportEnvelope | null;
  readonly error: string | null;
  readonly updatedAt: string;
}

interface WindowWithRegistry {
  __energySplitReports?: Record<string, BridgeRegistryEntry>;
}

const CARD_TYPE = "energy-split-history-bridge";
const EVENT_NAME = "energy-split-report";
const DEFAULT_POLL_SECONDS = 300;

function isValidConfig(raw: unknown): raw is HistoryBridgeConfig {
  if (typeof raw !== "object" || raw === null) {
    return false;
  }
  const cfg = raw as Record<string, unknown>;
  if (typeof cfg["id"] !== "string" || cfg["id"].length === 0) {
    return false;
  }
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

export class EnergySplitHistoryBridge extends HTMLElement {
  private _hass: HassLike | null = null;
  private _config: HistoryBridgeConfig | null = null;
  private _selection: SelectionState = INITIAL_SELECTION;
  private _lastEntry: BridgeRegistryEntry = {
    report: null,
    error: null,
    updatedAt: new Date(0).toISOString(),
  };
  private _fetchAbort: AbortController | null = null;
  private _pollTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly _root: ShadowRoot;

  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  static getStubConfig(): HistoryBridgeConfig {
    return {
      type: `custom:${CARD_TYPE}`,
      id: "primary",
      url: "/local/energy_split/report.json",
      poll_interval_seconds: DEFAULT_POLL_SECONDS,
    };
  }

  getCardSize(): number {
    return 1;
  }

  setConfig(config: unknown): void {
    if (!isValidConfig(config)) {
      throw new Error(t("error.invalid_config"));
    }
    this._config = config;
    this._selection = INITIAL_SELECTION;
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
      this._publish(null, raw.reason);
      return;
    }
    const parsed = await parseReport(raw.value);
    if (!parsed.ok) {
      this._publish(null, parsed.reason);
      return;
    }
    const envelope = parsed.value;
    if (!shouldAcceptSelection(this._selection, envelope.finalized_as_of)) {
      return;
    }
    this._selection = advanceSelection(this._selection, envelope.finalized_as_of);
    this._publish(envelope, null);
  }

  private _publish(report: ReportEnvelope | null, error: string | null): void {
    const config = this._config;
    if (config === null) {
      return;
    }
    const entry: BridgeRegistryEntry = {
      report,
      error,
      updatedAt: new Date().toISOString(),
    };
    const target = window as WindowWithRegistry;
    const registry = target.__energySplitReports ?? {};
    registry[config.id] = entry;
    target.__energySplitReports = registry;
    this._lastEntry = entry;
    this.dispatchEvent(
      new CustomEvent(EVENT_NAME, {
        bubbles: true,
        composed: true,
        detail: { id: config.id, entry },
      }),
    );
    this._render();
  }

  /**
   * Synchronous accessor for the last published entry. Sibling cards may
   * use this instead of the event when they render on demand.
   */
  static readEntry(id: string): BridgeRegistryEntry | null {
    const target = window as WindowWithRegistry;
    const registry = target.__energySplitReports ?? {};
    return registry[id] ?? null;
  }

  private _render(): void {
    const locale = resolveLocale(this._hass);
    const config = this._config;
    if (config === null) {
      this._root.innerHTML = `<style>${CARD_BASE_CSS}</style><div class="header">${escapeHtml(
        t("card.history_bridge.name", locale),
      )}</div>`;
      return;
    }
    const status =
      this._lastEntry.report === null
        ? this._lastEntry.error === null
          ? t("state.loading", locale)
          : t("state.unavailable", locale)
        : this._lastEntry.report.finalized_as_of;
    this._root.innerHTML = `
      <style>${CARD_BASE_CSS}</style>
      <div class="header">${escapeHtml(t("card.history_bridge.name", locale))}</div>
      <div class="row">
        <span class="label">id</span>
        <span class="value">${escapeHtml(config.id)}</span>
      </div>
      <div class="row">
        <span class="label">${escapeHtml(t("field.finalized_as_of", locale))}</span>
        <span class="value ${this._lastEntry.report === null ? "unavailable" : ""}">${escapeHtml(status)}</span>
      </div>
    `;
  }
}

defineCustomElementOnce(CARD_TYPE, EnergySplitHistoryBridge);
registerCustomCard({
  type: CARD_TYPE,
  name: t("card.history_bridge.name"),
  description: t("card.history_bridge.description"),
  preview: false,
});

export { EVENT_NAME as ENERGY_SPLIT_REPORT_EVENT };
