import {
  HISTORICAL_SERIES,
  buildHistoricalStatistics,
  isExactLocalDay,
  validateReport,
} from '/local/energy-split/energy-split-history-report.js';

/*
 * Presentation-only adapter for the existing energy-custom-graph-card.
 * It is opt-in, exact-day scoped, and never edits Recorder or live entities.
 */
(() => {
  const TAG = 'energy-custom-graph-card';
  const INSTALL_FLAG = '__energySplitHistoricalBridgeInstalledV2';

  const graphConfigIsExact = (instance) => {
    const config = instance._config;
    const series = Array.isArray(config?.series) ? config.series : [];
    const mapping = config?.historical_series;
    const ids = Object.keys(HISTORICAL_SERIES);
    if (config?.timespan?.mode !== 'energy' || config?.allow_compare === true
      || typeof config?.historical_data_url !== 'string'
      || !config.historical_data_url.trim()
      || typeof config?.historical_target_date !== 'string'
      || typeof config?.historical_timezone !== 'string'
      || !mapping || typeof mapping !== 'object'
      || Object.keys(mapping).sort().join('|') !== ids.slice().sort().join('|')) return false;
    if (series.length !== ids.length) return false;
    return ids.every((id) => mapping[id] === HISTORICAL_SERIES[id]
      && series.some((item) => item?.statistic_id === id && item?.stat_type === 'change'));
  };

  const snapshot = (instance) => ({
    periodStart: instance._periodStart?.getTime?.(),
    periodEnd: instance._periodEnd?.getTime?.() ?? null,
    rangeStart: instance._statisticsRange?.start,
    rangeEnd: instance._statisticsRange?.end ?? null,
  });

  const sameSnapshot = (instance, before) => {
    const after = snapshot(instance);
    return after.periodStart === before.periodStart
      && after.periodEnd === before.periodEnd
      && after.rangeStart === before.rangeStart
      && after.rangeEnd === before.rangeEnd;
  };

  const clearError = (instance) => {
    if (!instance.__energySplitHistoricalError) return;
    instance.__energySplitHistoricalError = false;
    instance._disabledMessage = undefined;
  };

  const failClosed = (instance, message) => {
    instance.__energySplitHistoricalError = true;
    instance._disabledMessage = `Історичні дані недоступні: ${message}`;
    // _statistics is reactive in the existing bundle. Clearing only this field
    // makes the existing graph show its disabled message without touching the
    // native metadata/range/aggregation state.
    instance._statistics = {};
  };

  const fetchValidatedReport = async (url) => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`звіт HTTP ${response.status}`);
    const validation = validateReport(await response.json());
    if (!validation.ok) throw new Error(validation.error);
    return validation;
  };

  const applyReport = async (instance) => {
    if (!graphConfigIsExact(instance)) return;
    const config = instance._config;
    const before = snapshot(instance);
    const start = instance._periodStart?.getTime?.();
    const end = instance._periodEnd?.getTime?.();
    if (!Number.isFinite(start) || !Number.isFinite(end)
      || instance._statisticsPeriod !== 'hour'
      || !isExactLocalDay(start, end, config.historical_target_date, config.historical_timezone)) {
      clearError(instance);
      return;
    }

    try {
      const validated = await fetchValidatedReport(config.historical_data_url.trim());
      if (validated.report.today_local !== config.historical_target_date
        || validated.report.timezone !== config.historical_timezone
        || !isExactLocalDay(start, end, validated.report.today_local, validated.report.timezone)) {
        throw new Error('звіт не відповідає вибраному локальному дню');
      }
      const built = buildHistoricalStatistics(validated, config.historical_series, start, end);
      if (!built.ok) throw new Error(built.error);
      if (!sameSnapshot(instance, before)) return;

      clearError(instance);
      // Atomic reactive replacement. Keep the card's native metadata and all
      // native period/aggregation fields untouched.
      instance._statistics = { ...(instance._statistics || {}), ...built.statistics };
    } catch (error) {
      if (!sameSnapshot(instance, before)) return;
      failClosed(instance, error instanceof Error ? error.message : String(error));
    }
  };

  const install = () => {
    const Card = customElements.get(TAG);
    if (!Card || !Card.prototype || Card.prototype[INSTALL_FLAG]) return Boolean(Card);
    const originalLoad = Card.prototype._loadStatistics;
    if (typeof originalLoad !== 'function') return false;
    Card.prototype[INSTALL_FLAG] = true;
    Card.prototype._loadStatistics = async function historicalAwareLoad(...args) {
      const result = await originalLoad.apply(this, args);
      if ((args[0] || 'main') === 'main') await applyReport(this);
      return result;
    };
    return true;
  };

  if (!install()) {
    customElements.whenDefined(TAG).then(install).catch((error) => {
      console.warn('[energy-split-history-bridge] card was not defined', error);
    });
  }
})();
