/* Energy Split period summary card v1.0.0
 * Read-only presentation card for the Energy Split dashboard.
 * It deliberately derives totals from the two authoritative child Recorder
 * statistics for the selected Energy Dashboard period. It never reads the
 * presentation aggregate entities and never calls a Home Assistant service.
 */
(() => {
  const TAG = 'energy-split-period-summary';
  const EPSILON = 1e-9;

  const escapeHtml = (value) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

  const asDate = (value) => {
    if (value instanceof Date) return new Date(value.getTime());
    if (typeof value === 'number' && Number.isFinite(value)) {
      return new Date(value < 1e12 ? value * 1000 : value);
    }
    if (typeof value === 'string') {
      const parsed = new Date(value);
      if (!Number.isNaN(parsed.getTime())) return parsed;
    }
    return null;
  };

  class EnergySplitPeriodSummary extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._config = null;
      this._unsubscribe = null;
      this._collection = null;
      this._requestGeneration = 0;
      this._selection = null;
      this._view = null;
    }

    setConfig(config) {
      if (!config || config.type !== `custom:${TAG}`) {
        throw new Error(`${TAG}: invalid card configuration`);
      }
      if (!config.collection_key || !/^energy_/.test(config.collection_key)) {
        throw new Error(`${TAG}: collection_key must be an energy_* collection`);
      }
      if (!config.entities || !config.entities.small || !config.entities.large) {
        throw new Error(`${TAG}: entities.small and entities.large are required`);
      }
      if (!config.expected_unit || !config.expected_unit_class) {
        throw new Error(`${TAG}: expected_unit and expected_unit_class are required`);
      }
      this._config = {
        title: config.title || 'Energy Split',
        collection_key: config.collection_key,
        entities: {
          small: config.entities.small,
          large: config.entities.large,
        },
        expected_unit: config.expected_unit,
        expected_unit_class: config.expected_unit_class,
        display_unit: config.display_unit || config.expected_unit,
        decimals: Number.isInteger(config.decimals) ? config.decimals : 2,
      };
      if (this._config.decimals < 0 || this._config.decimals > 4) {
        throw new Error(`${TAG}: decimals must be between 0 and 4`);
      }
      this._view = null;
      this._renderLoading('Очікую вибраний період…');
      this._ensureCollection();
    }

    set hass(value) {
      this._hass = value;
      this._ensureCollection();
    }

    get hass() {
      return this._hass;
    }

    connectedCallback() {
      this._ensureCollection();
    }

    disconnectedCallback() {
      this._unsubscribeCollection();
    }

    getCardSize() {
      return 2;
    }

    getGridOptions() {
      return { rows: 2, columns: 12, min_rows: 2 };
    }

    _unsubscribeCollection() {
      if (typeof this._unsubscribe === 'function') {
        try { this._unsubscribe(); } catch (_) { /* best effort cleanup */ }
      } else if (this._unsubscribe && typeof this._unsubscribe.unsubscribe === 'function') {
        try { this._unsubscribe.unsubscribe(); } catch (_) { /* best effort cleanup */ }
      }
      this._unsubscribe = null;
      this._collection = null;
    }

    _ensureCollection() {
      if (!this._hass || !this._config || !this._hass.connection) return;
      const key = `_${this._config.collection_key}`;
      const collection = this._hass.connection[key];
      if (!collection || typeof collection.subscribe !== 'function') {
        this._unsubscribeCollection();
        this._renderError('Вибір періоду Energy Dashboard недоступний. Дані не підмінено поточним станом.');
        return;
      }
      if (collection === this._collection) return;
      this._unsubscribeCollection();
      this._collection = collection;
      try {
        this._unsubscribe = collection.subscribe((selection) => this._onSelection(selection));
      } catch (error) {
        this._renderError(`Не вдалося підписатися на вибір періоду: ${error.message || error}`);
      }
    }

    _onSelection(selection) {
      if (!selection || !asDate(selection.start)) {
        this._renderError('Вибраний період недоступний.');
        return;
      }
      const start = asDate(selection.start);
      const selectedEnd = asDate(selection.end);
      // HA's date selector exposes the end of a selected day. The recorder
      // period is end-exclusive, so advance it by 1 ms, matching core cards.
      const end = selectedEnd ? new Date(selectedEnd.getTime() + 1) : new Date();
      if (!(end > start)) {
        this._renderError('Некоректні межі вибраного періоду.');
        return;
      }
      this._selection = { start, end };
      this._loadPeriod(start, end);
    }

    async _loadPeriod(start, end) {
      const generation = ++this._requestGeneration;
      this._renderLoading('Завантажую статистику вибраного періоду…');
      const ids = [this._config.entities.small, this._config.entities.large];
      try {
        const metadataResponse = await this._hass.callWS({
          type: 'recorder/get_statistics_metadata',
          statistic_ids: ids,
        });
        const metadata = Array.isArray(metadataResponse)
          ? metadataResponse
          : (metadataResponse?.result || []);
        const byId = new Map(metadata.map((item) => [item.statistic_id, item]));
        for (const id of ids) {
          const item = byId.get(id);
          const unit = item?.statistics_unit_of_measurement || item?.unit_of_measurement;
          const classMatches = item?.unit_class === this._config.expected_unit_class
            || (this._config.expected_unit_class === 'monetary' && item?.unit_class == null);
          if (!item || item.has_sum !== true || unit !== this._config.expected_unit || !classMatches) {
            throw new Error(`Немає сумісної sum-статистики для ${id}`);
          }
        }

        const responses = await Promise.all(ids.map((statistic_id) => this._hass.callWS({
          type: 'recorder/statistic_during_period',
          statistic_id,
          types: ['change'],
          fixed_period: {
            start_time: start.toISOString(),
            end_time: end.toISOString(),
          },
        })));
        if (generation !== this._requestGeneration) return;
        const values = responses.map((response, index) => {
          const result = response?.result || response;
          const value = Number(result?.change);
          if (!Number.isFinite(value)) {
            throw new Error(`Немає числової зміни для ${ids[index]}`);
          }
          if (value < -EPSILON) {
            throw new Error(`Виявлено відʼємну зміну для ${ids[index]}`);
          }
          return Math.abs(value) <= EPSILON ? 0 : value;
        });
        const unitScale = 10 ** this._config.decimals;
        const displayed = values.map((value) => Math.round(value * unitScale) / unitScale);
        const total = displayed[0] + displayed[1];
        this._view = { values: displayed, total, start, end };
        this._renderValue();
      } catch (error) {
        if (generation !== this._requestGeneration) return;
        this._view = null;
        this._renderError(`Помилка статистики: ${error.message || error}`);
      }
    }

    _cardShell(content) {
      const title = escapeHtml(this._config?.title || 'Energy Split');
      return `<style>
        :host { display:block; }
        ha-card { height:100%; overflow:hidden; }
        .header { padding:16px 16px 8px; font-size:1.05rem; font-weight:600; }
        .period { padding:0 16px 10px; color:var(--secondary-text-color); font-size:.78rem; }
        .grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; padding:8px 12px 14px; }
        .tile { min-width:0; border-radius:10px; background:var(--ha-card-background,var(--card-background-color)); padding:10px 8px; text-align:center; }
        .label { color:var(--secondary-text-color); font-size:.78rem; white-space:nowrap; }
        .value { color:var(--primary-text-color); font-size:1.35rem; font-weight:650; line-height:1.25; overflow-wrap:anywhere; }
        .unit { color:var(--secondary-text-color); font-size:.72rem; }
        .error { color:var(--error-color); padding:16px; line-height:1.4; }
        .loading { color:var(--secondary-text-color); padding:16px; }
        @media (max-width: 520px) { .grid { gap:5px; padding-left:8px; padding-right:8px; } .value { font-size:1.08rem; } .label { font-size:.7rem; } }
      </style><ha-card><div class="header">${title}</div>${content}</ha-card>`;
    }

    _renderLoading(message) {
      if (!this.shadowRoot) return;
      this.shadowRoot.innerHTML = this._cardShell(`<div class="loading">${escapeHtml(message)}</div>`);
    }

    _renderError(message) {
      if (!this.shadowRoot) return;
      this.shadowRoot.innerHTML = this._cardShell(`<div class="error">${escapeHtml(message)}</div>`);
    }

    _renderValue() {
      if (!this.shadowRoot || !this._view) return;
      const [small, large] = this._view.values;
      const total = this._view.total;
      const format = (value) => value.toFixed(this._config.decimals);
      const period = `${this._view.start.toLocaleString('uk-UA')} — ${this._view.end.toLocaleString('uk-UA')}`;
      const content = `<div class="period">${escapeHtml(period)}</div><div class="grid">
        <div class="tile"><div class="label">Малий</div><div class="value">${format(small)}</div><div class="unit">${escapeHtml(this._config.display_unit)}</div></div>
        <div class="tile"><div class="label">Великий</div><div class="value">${format(large)}</div><div class="unit">${escapeHtml(this._config.display_unit)}</div></div>
        <div class="tile"><div class="label">Разом</div><div class="value">${format(total)}</div><div class="unit">${escapeHtml(this._config.display_unit)}</div></div>
      </div>`;
      this.shadowRoot.innerHTML = this._cardShell(content);
    }
  }

  if (!customElements.get(TAG)) customElements.define(TAG, EnergySplitPeriodSummary);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: 'Energy Split Period Summary',
      description: 'Period-selected child statistics with an exact displayed total',
      preview: true,
    });
  }
})();
