export const HISTORICAL_SERIES = Object.freeze({
  'sensor.energy_small_home_total_cost_consistent': 'small_known_uah',
  'sensor.energy_parents_home_total_cost_consistent': 'parents_known_uah',
});

const REQUIRED_SCHEMA_VERSION = 1;
const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const EPSILON = 1e-7;

export const parseDate = (value) => {
  if (value instanceof Date) {
    const copy = new Date(value.getTime());
    return Number.isNaN(copy.getTime()) ? null : copy;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    const date = new Date(value < 1e12 ? value * 1000 : value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  if (typeof value === 'string' && value.trim()) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
};

const timezoneParts = (date, timezone) => {
  if (!(date instanceof Date) || Number.isNaN(date.getTime()) || typeof timezone !== 'string') return null;
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      calendar: 'gregory',
      numberingSystem: 'latn',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date);
    const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]));
    return {
      year: values.year,
      month: values.month,
      day: values.day,
      hour: values.hour,
      minute: values.minute,
      second: values.second,
    };
  } catch (_) {
    return null;
  }
};

export const localDateKey = (value, timezone) => {
  const parts = timezoneParts(parseDate(value), timezone);
  return parts ? `${parts.year}-${parts.month}-${parts.day}` : null;
};

const nextDateKey = (dateKey) => {
  const date = new Date(`${dateKey}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
};

export const isExactLocalDay = (startValue, endValue, targetDate, timezone) => {
  const start = parseDate(startValue);
  const end = parseDate(endValue);
  if (!start || !end || end <= start || typeof targetDate !== 'string'
    || !/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) return false;
  const startParts = timezoneParts(start, timezone);
  const endMinusOneParts = timezoneParts(new Date(end.getTime() - 1), timezone);
  const endParts = timezoneParts(end, timezone);
  if (!startParts || !endMinusOneParts || !endParts) return false;
  if (startParts.hour !== '00' || startParts.minute !== '00' || startParts.second !== '00'
    || start.getMilliseconds() !== 0) return false;
  const startKey = `${startParts.year}-${startParts.month}-${startParts.day}`;
  const endMinusOneKey = `${endMinusOneParts.year}-${endMinusOneParts.month}-${endMinusOneParts.day}`;
  const endKey = `${endParts.year}-${endParts.month}-${endParts.day}`;
  const normalEnd = endMinusOneKey === targetDate;
  // The summary card normalizes an inclusive selector end by adding 1 ms. Also
  // accept that representation when it lands exactly at next local midnight.
  const inclusiveEndAdjustment = endKey === nextDateKey(targetDate)
    && endParts.hour === '00' && endParts.minute === '00' && endParts.second === '00'
    && end.getMilliseconds() <= 1;
  return startKey === targetDate && (normalEnd || inclusiveEndAdjustment)
    && end.getTime() - start.getTime() <= 25 * HOUR_MS
    && end.getTime() - start.getTime() >= 23 * HOUR_MS;
};

const finiteNonnegative = (value) => Number.isFinite(Number(value)) && Number(value) >= -EPSILON;
const closeEnough = (left, right) => Math.abs(left - right) <= Math.max(EPSILON, Math.abs(right) * 1e-8);
const invalid = (message) => ({ ok: false, error: message });

export const validateReport = (report) => {
  if (!report || typeof report !== 'object' || Array.isArray(report)) return invalid('звіт має бути JSON-обʼєктом');
  if (report.schema_version !== REQUIRED_SCHEMA_VERSION) return invalid('непідтримувана версія звіту');
  if (typeof report.timezone !== 'string' || !report.timezone.trim()) return invalid('у звіті відсутня timezone');
  if (typeof report.today_local !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(report.today_local)) {
    return invalid('у звіті відсутня коректна today_local');
  }
  const reportStart = parseDate(report.period_start_utc);
  const reportEnd = parseDate(report.period_end_utc);
  if (!reportStart || !reportEnd || reportEnd <= reportStart) return invalid('некоректні межі звіту');
  if (localDateKey(reportStart, report.timezone) !== report.today_local
    || localDateKey(new Date(reportEnd.getTime() - 1), report.timezone) !== report.today_local) {
    return invalid('межі звіту не відповідають today_local');
  }
  const rows = Array.isArray(report.hourly) ? report.hourly : [];
  if (!rows.length) return invalid('у звіті немає погодинних рядків');
  const seen = new Set();
  let previousStart = -Infinity;
  let small = 0;
  let parents = 0;
  for (const row of rows) {
    if (!row || typeof row !== 'object') return invalid('погодинний рядок має бути обʼєктом');
    const start = parseDate(row.hour_local);
    const startMs = start?.getTime();
    if (!Number.isFinite(startMs) || startMs < previousStart) return invalid('погодинні рядки не відсортовані');
    const key = start.toISOString();
    if (seen.has(key) || localDateKey(start, report.timezone) !== report.today_local) {
      return invalid('погодинні рядки мають дублікати або іншу дату');
    }
    seen.add(key);
    previousStart = startMs;
    for (const field of ['small_known_uah', 'parents_known_uah', 'known_uah', 'coverage_fraction']) {
      if (!finiteNonnegative(row[field])) return invalid(`некоректне поле ${field}`);
    }
    if (Number(row.coverage_fraction) > 1 + EPSILON) return invalid('coverage_fraction поза межами 0..1');
    const rowSmall = Math.max(0, Number(row.small_known_uah));
    const rowParents = Math.max(0, Number(row.parents_known_uah));
    const rowKnown = Math.max(0, Number(row.known_uah));
    if (!closeEnough(rowSmall + rowParents, rowKnown)) return invalid('погодинний total не дорівнює сумі будинків');
    small += rowSmall;
    parents += rowParents;
  }
  const total = report.total;
  if (!total || !finiteNonnegative(total.small_known_uah)
    || !finiteNonnegative(total.parents_known_uah) || !finiteNonnegative(total.known_uah)
    || !finiteNonnegative(total.coverage_fraction) || Number(total.coverage_fraction) > 1 + EPSILON) {
    return invalid('некоректний total звіту');
  }
  const totalSmall = Math.max(0, Number(total.small_known_uah));
  const totalParents = Math.max(0, Number(total.parents_known_uah));
  const totalKnown = Math.max(0, Number(total.known_uah));
  if (!closeEnough(small, totalSmall) || !closeEnough(parents, totalParents)
    || !closeEnough(totalSmall + totalParents, totalKnown)) {
    return invalid('total звіту не відповідає погодинним рядкам');
  }
  return {
    ok: true,
    report,
    reportStart,
    reportEnd,
    rows,
    total: {
      small_known_uah: totalSmall,
      parents_known_uah: totalParents,
      known_uah: totalKnown,
      coverage_fraction: Math.max(0, Math.min(1, Number(total.coverage_fraction))),
    },
  };
};

export const buildHistoricalStatistics = (validated, mapping, startValue, endValue) => {
  if (!validated?.ok || !mapping || typeof mapping !== 'object') return invalid('відсутнє mapping історичних серій');
  const ids = Object.keys(HISTORICAL_SERIES);
  const mappingKeys = Object.keys(mapping).sort();
  if (mappingKeys.length !== ids.length || mappingKeys.some((id, index) => id !== ids.slice().sort()[index])) {
    return invalid('mapping має містити рівно дві cost-серії');
  }
  for (const id of ids) {
    if (mapping[id] !== HISTORICAL_SERIES[id]) return invalid(`mapping не дозволяє серію ${id}`);
  }
  const start = parseDate(startValue)?.getTime();
  const end = parseDate(endValue)?.getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return invalid('некоректний період серій');
  const result = {};
  const startsById = [];
  for (const id of ids) {
    const field = mapping[id];
    const rows = validated.rows.filter((row) => {
      const rowStart = parseDate(row.hour_local)?.getTime();
      return Number.isFinite(rowStart) && rowStart >= start && rowStart < end;
    });
    if (!rows.length) return invalid(`немає рядків для ${id}`);
    const stats = rows.map((row) => {
      const rowStart = parseDate(row.hour_local).getTime();
      const value = Number(row[field]);
      if (!Number.isFinite(value) || value < -EPSILON) return null;
      return {
        start: rowStart,
        end: rowStart + HOUR_MS,
        change: Math.max(0, value),
        sum: null,
        mean: null,
        min: null,
        max: null,
        state: null,
      };
    });
    if (stats.some((row) => row === null)) return invalid(`некоректні значення для ${id}`);
    result[id] = stats;
    startsById.push(stats.map((row) => row.start).join(','));
  }
  if (startsById[0] !== startsById[1]) return invalid('серії мають різні часові рядки');
  return { ok: true, statistics: result };
};
