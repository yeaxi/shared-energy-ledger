/**
 * Monotonic selection guard used by every card that renders a period report.
 *
 * REQUIREMENTS.md invariant I8 forbids overwriting a newer selection with an
 * older asynchronous result. Cards MUST call `shouldAcceptSelection` before
 * commiting a fetched report to their state; when the guard returns `false`
 * the fetched report is discarded and the previous state kept intact.
 *
 * The guard is intentionally string-based so it can compare
 * `finalized_as_of` values without parsing them. ISO-8601 UTC timestamps
 * with fixed offsets sort lexicographically the same way they sort
 * chronologically.
 */

export interface SelectionState {
  readonly finalizedAsOf: string | null;
}

/**
 * Return whether a freshly fetched report should replace the currently
 * selected one. `nextFinalizedAsOf` must be an ISO-8601 UTC timestamp
 * ending in "Z" (see `custom_components/shared_energy_ledger/report.py::_to_iso_utc`).
 */
export function shouldAcceptSelection(
  previous: SelectionState,
  nextFinalizedAsOf: string,
): boolean {
  if (typeof nextFinalizedAsOf !== "string" || nextFinalizedAsOf.length === 0) {
    return false;
  }
  if (!nextFinalizedAsOf.endsWith("Z")) {
    return false;
  }
  const previousValue = previous.finalizedAsOf;
  if (previousValue === null || previousValue.length === 0) {
    return true;
  }
  return nextFinalizedAsOf > previousValue;
}

/**
 * Helper that both checks the guard and returns the next selection state.
 * Cards can store the returned state directly.
 */
export function advanceSelection(
  previous: SelectionState,
  nextFinalizedAsOf: string,
): SelectionState {
  if (!shouldAcceptSelection(previous, nextFinalizedAsOf)) {
    return previous;
  }
  return { finalizedAsOf: nextFinalizedAsOf };
}

export const INITIAL_SELECTION: SelectionState = { finalizedAsOf: null };
