import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = path.resolve(new URL('..', import.meta.url).pathname);
const report = JSON.parse(fs.readFileSync(path.join(root, 'reports/energy_cost_2026-08-05.json'), 'utf8'));
const dayStart = new Date('2026-08-04T21:00:00.000Z');
const dayEnd = new Date('2026-08-05T21:00:00.000Z');

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'energy-split-history-'));
const sharedSource = fs.readFileSync(path.join(root, 'frontend/energy-split-history-report.js'), 'utf8');
const bridgeSource = fs.readFileSync(path.join(root, 'frontend/energy-split-history-bridge.js'), 'utf8')
  .replace("'/local/energy-split/energy-split-history-report.js'", "'./history-report.mjs'");
const summarySource = fs.readFileSync(path.join(root, 'frontend/energy-split-period-summary.js'), 'utf8')
  .replace("'/local/energy-split/energy-split-history-report.js'", "'./history-report.mjs'");
fs.writeFileSync(path.join(temp, 'history-report.mjs'), sharedSource);
fs.writeFileSync(path.join(temp, 'bridge.mjs'), bridgeSource);
fs.writeFileSync(path.join(temp, 'summary.mjs'), summarySource);

const shared = await import(pathToFileURL(path.join(temp, 'history-report.mjs')));
assert.equal(shared.validateReport(report).ok, true);
const missingContract = structuredClone(report);
delete missingContract.report_revision;
delete missingContract.finalized_at_utc;
assert.equal(shared.validateReport(missingContract).ok, false, 'immutable report contract is required');
const strictTypes = structuredClone(report);
strictTypes.hourly[0].small_known_uah = '0';
assert.equal(shared.validateReport(strictTypes).ok, false, 'numeric fields must not coerce strings');
const booleanValue = structuredClone(report);
booleanValue.hourly[0].small_known_uah = true;
assert.equal(shared.validateReport(booleanValue).ok, false, 'boolean fields must fail closed');
const nullCoverage = structuredClone(report);
nullCoverage.total.coverage_fraction = null;
assert.equal(shared.validateReport(nullCoverage).ok, false, 'null coverage must fail closed');
const outOfPeriod = structuredClone(report);
outOfPeriod.hourly[0].hour_local = '2026-08-05T20:00:00+0300';
assert.equal(shared.validateReport(outOfPeriod).ok, false, 'rows after period_end must fail closed');
const inconsistentCoverage = structuredClone(report);
inconsistentCoverage.total.coverage_fraction = 0.1;
assert.equal(shared.validateReport(inconsistentCoverage).ok, false, 'coverage must match covered seconds and period');
const prematureFinalized = structuredClone(report);
prematureFinalized.finalized_at_utc = prematureFinalized.period_end_utc;
assert.equal(shared.validateReport(prematureFinalized).ok, false, 'finalized-as-of must not precede generated_at');
assert.equal(shared.isExactLocalDay(dayStart, dayEnd, '2026-08-05', 'Europe/Kyiv'), true);
assert.equal(shared.isExactLocalDay(
  new Date('2026-08-05T09:00:00.000Z'),
  new Date('2026-08-06T09:00:00.000Z'),
  '2026-08-05',
  'Europe/Kyiv',
), false, 'midday-to-midday overlap must not be treated as a day');
assert.equal(shared.isExactLocalDay(
  new Date('2026-08-04T21:00:00.000Z'),
  new Date('2026-08-05T18:00:00.000Z'),
  '2026-08-05',
  'Europe/Kyiv',
), false, 'same-day 23:00 end must not be treated as a full day');
assert.equal(shared.isExactLocalDay(
  new Date('2026-03-08T05:00:00.000Z'),
  new Date('2026-03-09T04:00:00.000Z'),
  '2026-03-08',
  'America/New_York',
), true, 'spring-forward day is a valid 23-hour local day');
assert.equal(shared.isExactLocalDay(
  new Date('2026-11-01T04:00:00.000Z'),
  new Date('2026-11-02T05:00:00.000Z'),
  '2026-11-01',
  'America/New_York',
), true, 'fall-back day is a valid 25-hour local day');

const validated = shared.validateReport(report);
const built = shared.buildHistoricalStatistics(
  validated,
  shared.HISTORICAL_SERIES,
  dayStart.getTime(),
  dayEnd.getTime(),
);
assert.equal(built.ok, true);
assert.equal(built.report_revision, report.report_revision, 'graph output keeps immutable report revision');
for (const rows of Object.values(built.statistics)) {
  assert.ok(rows.length > 0);
  assert.ok(rows.every((row) => row.sum === null && row.mean === null
    && row.min === null && row.max === null && row.state === null));
}
const malformed = structuredClone(report);
delete malformed.hourly[0].parents_known_uah;
assert.equal(shared.validateReport(malformed).ok, false, 'missing parent series must fail closed');
const mismatched = structuredClone(report);
mismatched.total.known_uah += 1;
assert.equal(shared.validateReport(mismatched).ok, false, 'mismatched total must fail closed');
const unitScale = 100;
const displayed = [report.total.small_known_uah, report.total.parents_known_uah]
  .map((value) => Math.round(value * unitScale) / unitScale);
assert.equal(displayed[0] + displayed[1], Math.round((displayed[0] + displayed[1]) * unitScale) / unitScale);

class FakeCard {
  async _loadStatistics() {
    return 'native-loaded';
  }
}
const registry = new Map([['energy-custom-graph-card', FakeCard]]);
globalThis.customElements = {
  get: (name) => registry.get(name),
  define: (name, constructor) => registry.set(name, constructor),
  whenDefined: async (name) => registry.get(name),
};
globalThis.HTMLElement = class {
  attachShadow() {
    return { innerHTML: '' };
  }
};
globalThis.window = {};
let fetchCalls = 0;
globalThis.fetch = async () => {
  fetchCalls += 1;
  return { ok: true, json: async () => report };
};
await import(`${pathToFileURL(path.join(temp, 'bridge.mjs')).href}?v=1`);

const makeInstance = (start = dayStart, end = dayEnd) => {
  const instance = new FakeCard();
  instance._config = {
    timespan: { mode: 'energy' },
    allow_compare: false,
    historical_data_url: '/local/energy-split/energy_cost_2026-08-05.json',
    historical_target_date: '2026-08-05',
    historical_timezone: 'Europe/Kyiv',
    historical_series: { ...shared.HISTORICAL_SERIES },
    series: Object.keys(shared.HISTORICAL_SERIES).map((statistic_id) => ({
      statistic_id,
      stat_type: 'change',
    })),
  };
  instance._periodStart = new Date(start);
  instance._periodEnd = new Date(end);
  instance._statisticsPeriod = 'hour';
  instance._statisticsRange = { start: instance._periodStart.getTime(), end: instance._periodEnd.getTime() };
  instance._statistics = {
    [Object.keys(shared.HISTORICAL_SERIES)[0]]: [{ start: 1, change: 99 }],
    [Object.keys(shared.HISTORICAL_SERIES)[1]]: [{ start: 1, change: 98 }],
  };
  instance._metadata = { preserved: true };
  return instance;
};

const normal = makeInstance();
const originalMetadata = normal._metadata;
await normal._loadStatistics('main');
assert.equal(fetchCalls, 1);
assert.equal(normal._metadata, originalMetadata, 'bridge must not replace metadata');
assert.equal(normal._statisticsRange.start, dayStart.getTime());
assert.equal(normal._statistics[Object.keys(shared.HISTORICAL_SERIES)[0]][0].sum, null);

const overlap = makeInstance(new Date('2026-08-05T09:00:00.000Z'), new Date('2026-08-06T09:00:00.000Z'));
const callsBeforeOverlap = fetchCalls;
await overlap._loadStatistics('main');
assert.equal(fetchCalls, callsBeforeOverlap, 'non-day range must not fetch historical data');
assert.equal(overlap._statistics[Object.keys(shared.HISTORICAL_SERIES)[0]][0].change, 99);

let release;
globalThis.fetch = () => new Promise((resolve) => {
  release = () => resolve({ ok: true, json: async () => report });
});
const raced = makeInstance();
const racePromise = raced._loadStatistics('main');
await new Promise((resolve) => setImmediate(resolve));
raced._periodStart = new Date('2026-08-05T09:00:00.000Z');
raced._periodEnd = new Date('2026-08-06T09:00:00.000Z');
await raced._loadStatistics('main');
raced._periodStart = new Date(dayStart);
raced._periodEnd = new Date(dayEnd);
assert.equal(typeof release, 'function', 'race fetch must be started');
release();
await racePromise;
assert.equal(raced._statistics[Object.keys(shared.HISTORICAL_SERIES)[0]][0].change, 99, 'ABA race must not apply stale rows');

const partial = structuredClone(report);
delete partial.hourly[0].parents_known_uah;
globalThis.fetch = async () => ({ ok: true, json: async () => partial });
const failed = makeInstance();
await failed._loadStatistics('main');
assert.deepEqual(failed._statistics, {}, 'invalid target-day report must fail closed');
assert.match(failed._disabledMessage, /Історичні дані недоступні/);

await import(`${pathToFileURL(path.join(temp, 'summary.mjs')).href}?v=1`);
const SummaryCard = registry.get('energy-split-period-summary');
const summary = new SummaryCard();
summary.setConfig({
  type: 'custom:energy-split-period-summary',
  collection_key: 'energy_split_dashboard',
  entities: { small: 'small', large: 'large' },
  expected_unit: 'UAH',
  expected_unit_class: 'monetary',
  historical_data_url: '/local/energy-split/energy_cost_2026-08-05.json',
  historical_target_date: '2026-08-05',
  historical_timezone: 'Europe/Kyiv',
  decimals: 2,
});
globalThis.fetch = async () => ({ ok: true, json: async () => report });
const summaryView = await summary._loadHistoricalPeriod(dayStart, new Date(dayEnd.getTime() + 1));
assert.equal(summaryView.values[0], Math.round(report.total.small_known_uah * 100) / 100);
assert.equal(summaryView.values[1], Math.round(report.total.parents_known_uah * 100) / 100);
assert.equal(summaryView.total, summaryView.values[0] + summaryView.values[1], 'displayed total must equal displayed components');
assert.equal(summaryView.revision, report.report_revision, 'summary keeps the same immutable report revision');
let releaseSummary;
globalThis.fetch = () => new Promise((resolve) => {
  releaseSummary = () => resolve({ ok: true, json: async () => report });
});
const summaryRace = new SummaryCard();
summaryRace.setConfig({
  type: 'custom:energy-split-period-summary',
  collection_key: 'energy_split_dashboard',
  entities: { small: 'small', large: 'large' },
  expected_unit: 'UAH',
  expected_unit_class: 'monetary',
  historical_data_url: '/local/energy-split/energy_cost_2026-08-05.json',
  historical_target_date: '2026-08-05',
  historical_timezone: 'Europe/Kyiv',
  decimals: 2,
});
const summaryRacePromise = summaryRace._loadPeriod(dayStart, new Date(dayEnd.getTime() + 1));
await new Promise((resolve) => setImmediate(resolve));
summaryRace.setConfig({
  type: 'custom:energy-split-period-summary',
  collection_key: 'energy_split_dashboard',
  entities: { small: 'small', large: 'large' },
  expected_unit: 'UAH',
  expected_unit_class: 'monetary',
  historical_data_url: '/local/energy-split/energy_cost_2026-08-05.json',
  historical_target_date: '2026-08-06',
  historical_timezone: 'Europe/Kyiv',
  decimals: 2,
});
assert.equal(typeof releaseSummary, 'function', 'summary race fetch must be started');
releaseSummary();
await summaryRacePromise;
assert.equal(summaryRace._view, null, 'summary config race must not apply stale report');
globalThis.fetch = async () => ({ ok: true, json: async () => partial });
const originalWarn = console.warn;
console.warn = () => {};
const summaryError = await summary._loadHistoricalPeriod(dayStart, dayEnd);
console.warn = originalWarn;
assert.match(summaryError.error, /не вдалося перевірити звіт/);

fs.rmSync(temp, { recursive: true, force: true });
console.log('historical_frontend_behavior=ok');
