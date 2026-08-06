export const HISTORICAL_SERIES = Object.freeze({
  'sensor.energy_small_home_total_cost_consistent': 'small_known_uah',
  'sensor.energy_parents_home_total_cost_consistent': 'parents_known_uah',
});

const SUPPORTED_SCHEMA_VERSIONS = new Set([1, 2]);
const HOUR_MS = 60 * 60 * 1000;
const EPSILON = 1e-7;
const REPORT_REVISION_RE = /^[a-f0-9]{64}$/;

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

const isMidnight = (parts, date) => parts?.hour === '00'
  && parts.minute === '00'
  && parts.second === '00'
  && date.getMilliseconds() === 0;

const isInclusiveMidnight = (parts, date) => parts?.hour === '00'
  && parts.minute === '00'
  && parts.second === '00'
  && date.getMilliseconds() <= 1;

export const isExactLocalDay = (startValue, endValue, targetDate, timezone) => {
  const start = parseDate(startValue);
  const end = parseDate(endValue);
  if (!start || !end || end <= start || typeof targetDate !== 'string'
    || !/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) return false;
  const startParts = timezoneParts(start, timezone);
  const endParts = timezoneParts(end, timezone);
  if (!startParts || !endParts || !isMidnight(startParts, start)) return false;
  const startKey = `${startParts.year}-${startParts.month}-${startParts.day}`;
  const endKey = `${endParts.year}-${endParts.month}-${endParts.day}`;
  const nextKey = nextDateKey(targetDate);
  const exactEnd = endKey === nextKey && isMidnight(endParts, end);
  const inclusiveEndAdjustment = endKey === nextKey && isInclusiveMidnight(endParts, end);
  const duration = end.getTime() - start.getTime();
  return startKey === targetDate
    && (exactEnd || inclusiveEndAdjustment)
    && duration >= 23 * HOUR_MS
    && duration <= 25 * HOUR_MS + 1;
};

const strictFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value);
const strictNonnegative = (value) => strictFiniteNumber(value) && value >= -EPSILON;
const closeEnough = (left, right) => Math.abs(left - right) <= Math.max(EPSILON, Math.abs(right) * 1e-8);
const normalizedNonnegative = (value) => value < 0 ? 0 : value;
const invalid = (message) => ({ ok: false, error: message });

export const validateReport = (report) => {
  if (!report || typeof report !== 'object' || Array.isArray(report)) return invalid('звіт має бути JSON-обʼєктом');
  if (!SUPPORTED_SCHEMA_VERSIONS.has(report.schema_version)) return invalid('непідтримувана версія звіту');
  const hasProvenanceV2 = report.schema_version === 2;
  if (hasProvenanceV2 && report.provenance_schema !== 'direct_allocation_v1') {
    return invalid('у звіті відсутня provenance schema');
  }
  if (typeof report.timezone !== 'string' || !report.timezone.trim()) return invalid('у звіті відсутня timezone');
  if (typeof report.today_local !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(report.today_local)) {
    return invalid('у звіті відсутня коректна today_local');
  }
  if (typeof report.report_revision !== 'string' || !REPORT_REVISION_RE.test(report.report_revision)) {
    return invalid('у звіті відсутня immutable report_revision');
  }
  const reportStart = parseDate(report.period_start_utc);
  const reportEnd = parseDate(report.period_end_utc);
  const generatedAt = parseDate(report.generated_at_utc);
  const finalizedAt = parseDate(report.finalized_at_utc);
  if (typeof report.generated_at_utc !== 'string' || typeof report.finalized_at_utc !== 'string'
    || !reportStart || !reportEnd || reportEnd <= reportStart || !generatedAt || !finalizedAt) {
    return invalid('некоректні часові межі або finalized-as-of звіту');
  }
  const reportStartParts = timezoneParts(reportStart, report.timezone);
  const reportEndParts = timezoneParts(reportEnd, report.timezone);
  const reportEndMinusOneKey = localDateKey(new Date(reportEnd.getTime() - 1), report.timezone);
  const reportEndKey = localDateKey(reportEnd, report.timezone);
  const reportNextKey = nextDateKey(report.today_local);
  const reportEndAtNextMidnight = reportEndKey === reportNextKey
    && reportEndParts?.hour === '00'
    && reportEndParts.minute === '00'
    && reportEndParts.second === '00'
    && reportEnd.getMilliseconds() === 0;
  if (!reportStartParts || !isMidnight(reportStartParts, reportStart)
    || localDateKey(reportStart, report.timezone) !== report.today_local
    || (reportEndMinusOneKey !== report.today_local && !reportEndAtNextMidnight)
    || generatedAt.getTime() < reportEnd.getTime()
    || finalizedAt.getTime() < generatedAt.getTime()) {
    return invalid('межі або finalized-as-of звіту не відповідають today_local');
  }

  const reportDuration = reportEnd.getTime() - reportStart.getTime();
  const reportDurationSeconds = reportDuration / 1000;
  const rows = Array.isArray(report.hourly) ? report.hourly : [];
  if (!rows.length) return invalid('у звіті немає погодинних рядків');
  const seen = new Set();
  let previousStart = -Infinity;
  let rowCoverageSeconds = 0;
  let rowDirectAllocationSeconds = 0;
  let rowDerivedAllocationSeconds = 0;
  let rowTransitionExcludedSeconds = 0;
  let small = 0;
  let parents = 0;
  for (const row of rows) {
    if (!row || typeof row !== 'object' || typeof row.hour_local !== 'string') {
      return invalid('погодинний рядок має бути обʼєктом');
    }
    const start = parseDate(row.hour_local);
    const startMs = start?.getTime();
    if (!Number.isFinite(startMs) || startMs < reportStart.getTime()
      || startMs >= reportEnd.getTime() || startMs < previousStart) {
      return invalid('погодинний рядок виходить за межі звіту');
    }
    const key = start.toISOString();
    if (seen.has(key) || localDateKey(start, report.timezone) !== report.today_local) {
      return invalid('погодинні рядки мають дублікати або іншу дату');
    }
    seen.add(key);
    previousStart = startMs;
    for (const field of ['small_known_uah', 'parents_known_uah', 'known_uah', 'coverage_seconds', 'coverage_fraction']) {
      if (!strictNonnegative(row[field])) return invalid(`некоректне поле ${field}`);
    }
    if (hasProvenanceV2) {
      for (const field of ['direct_allocation_seconds', 'derived_allocation_seconds', 'source_transition_excluded_seconds']) {
        if (!strictNonnegative(row[field])) return invalid(`некоректне provenance поле ${field}`);
      }
      if (!closeEnough(
        row.direct_allocation_seconds + row.derived_allocation_seconds,
        row.coverage_seconds,
      )) return invalid('погодинний provenance total не дорівнює coverage');
      rowDirectAllocationSeconds += row.direct_allocation_seconds;
      rowDerivedAllocationSeconds += row.derived_allocation_seconds;
      rowTransitionExcludedSeconds += row.source_transition_excluded_seconds;
    }
    if (row.coverage_seconds > 3600 + EPSILON || row.coverage_fraction > 1 + EPSILON
      || !closeEnough(row.coverage_fraction, row.coverage_seconds / 3600)) {
      return invalid('некоректне погодинне coverage');
    }
    const rowSmall = normalizedNonnegative(row.small_known_uah);
    const rowParents = normalizedNonnegative(row.parents_known_uah);
    const rowKnown = normalizedNonnegative(row.known_uah);
    if (!closeEnough(rowSmall + rowParents, rowKnown)) return invalid('погодинний total не дорівнює сумі будинків');
    rowCoverageSeconds += row.coverage_seconds;
    small += rowSmall;
    parents += rowParents;
  }

  const total = report.total;
  if (hasProvenanceV2 && (!total
    || !strictNonnegative(total.direct_allocation_seconds)
    || !strictNonnegative(total.derived_allocation_seconds)
    || !strictNonnegative(total.source_transition_excluded_seconds))) {
    return invalid('у total відсутня provenance coverage');
  }
  if (hasProvenanceV2 && !closeEnough(
    total.direct_allocation_seconds + total.derived_allocation_seconds,
    total.coverage_seconds,
  )) return invalid('total provenance не дорівнює coverage');
  if (hasProvenanceV2 && (!closeEnough(rowDirectAllocationSeconds, total.direct_allocation_seconds)
    || !closeEnough(rowDerivedAllocationSeconds, total.derived_allocation_seconds)
    || !closeEnough(rowTransitionExcludedSeconds, total.source_transition_excluded_seconds))) {
    return invalid('total provenance не відповідає погодинним рядкам');
  }
  if (!total || !strictNonnegative(total.small_known_uah)
    || !strictNonnegative(total.parents_known_uah) || !strictNonnegative(total.known_uah)
    || !strictNonnegative(total.coverage_seconds) || !strictNonnegative(total.coverage_fraction)
    || !Number.isInteger(total.valid_sample_count) || !Number.isInteger(total.sample_count)
    || total.valid_sample_count < 0 || total.sample_count < 1
    || total.valid_sample_count > total.sample_count
    || total.coverage_seconds > reportDurationSeconds + EPSILON
    || total.coverage_fraction > 1 + EPSILON
    || !closeEnough(rowCoverageSeconds, total.coverage_seconds)
    || !closeEnough(total.coverage_fraction, total.coverage_seconds / reportDurationSeconds)) {
    return invalid('некоректний або неузгоджений total звіту');
  }
  const totalSmall = normalizedNonnegative(total.small_known_uah);
  const totalParents = normalizedNonnegative(total.parents_known_uah);
  const totalKnown = normalizedNonnegative(total.known_uah);
  if (!closeEnough(small, totalSmall) || !closeEnough(parents, totalParents)
    || !closeEnough(totalSmall + totalParents, totalKnown)) {
    return invalid('total звіту не відповідає погодинним рядкам');
  }
  return {
    ok: true,
    report,
    reportStart,
    reportEnd,
    generatedAt,
    finalizedAt,
    rows,
    report_revision: report.report_revision,
    total: {
      small_known_uah: totalSmall,
      parents_known_uah: totalParents,
      known_uah: totalKnown,
      coverage_fraction: normalizedNonnegative(Math.min(1, total.coverage_fraction)),
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
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start
    || !isExactLocalDay(start, end, validated.report.today_local, validated.report.timezone)) {
    return invalid('некоректний або не exact-local-day період серій');
  }
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
      const value = row[field];
      if (!strictFiniteNumber(value) || value < -EPSILON) return null;
      return {
        start: rowStart,
        end: rowStart + HOUR_MS,
        change: normalizedNonnegative(value),
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
  return { ok: true, statistics: result, report_revision: validated.report_revision };
};
