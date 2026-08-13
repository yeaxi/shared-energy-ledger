# Traceability matrix

Each invariant from [`REQUIREMENTS.md#a3`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md#a3-non-functional-invariants)
is covered by at least one test module under `tests/`. The mapping below is
enforced by
[`scripts/check_requirements_traceability.py`](https://github.com/yeaxi/shared-energy-ledger/blob/main/scripts/check_requirements_traceability.py),
which fails CI when an invariant identifier is missing from `tests/` or from
this matrix, or when this matrix cites a test module that no longer exists.

## Mapping

| Invariant | Description (short) | Test modules |
| --- | --- | --- |
| `I1` | No silent zero. | `tests/unit/test_interval.py`, `tests/unit/test_allocation.py`, `tests/unit/test_ledger.py`, `tests/unit/test_samples.py`, `tests/integration/test_sensors.py` |
| `I2` | Per-data-class freshness. | `tests/unit/test_samples.py`, `tests/integration/test_coordinator.py` |
| `I3` | Closed allocation enum. | `tests/unit/test_allocation.py`, `tests/unit/test_allocation_exhaustive.py` |
| `I4` | Residual fallback rules. | `tests/unit/test_allocation.py` |
| `I5` | Recorder unit metadata is validated. | `tests/unit/test_samples.py`, `tests/integration/test_coordinator.py` |
| `I6` | Battery ledger safety. | `tests/unit/test_ledger.py`, `tests/unit/test_ledger_store.py`, `tests/integration/test_battery_ledger_flow.py` |
| `I7` | Report source-split contract and unpriced battery energy. | `tests/unit/test_report.py`, `tests/unit/test_interval.py`, `tests/integration/test_rebuild_period_report.py` |
| `I8` | Async selection ordering (monotonic request id). | `tests/unit/test_report.py`, `dashboard/tests/report.test.ts` |
| `I9` | Config-entry migration and stable identity. | `tests/integration/test_setup.py`, `tests/unit/test_configio.py`, `tests/integration/test_options_flow_menu.py` |
| `I10` | Dashboards fail closed. | `dashboard/tests/report.test.ts` |

`I8` (card selection ordering) and `I10` (fail-closed rendering) are covered by
the frontend card contract tests in the `dashboard/` package. The Python
`test_report.py` covers the revision-hash and finalized-as-of half of `I8`.

## Adding a new invariant

When a new invariant is added:

1. Update [`REQUIREMENTS.md`](https://github.com/yeaxi/shared-energy-ledger/blob/main/REQUIREMENTS.md)
   with the new identifier (`I11`, `I12`, ...).
2. Add or extend a test module under `tests/` that references the new
   identifier at least once.
3. Add the invariant to [invariants.md](invariants.md) with the verbatim
   wording and a plain-language note.
4. Extend the table above with the covering test modules.
5. Rerun `python scripts/check_requirements_traceability.py` locally to confirm
   CI will pass.

## Retiring an invariant

Retiring an invariant is a **breaking change** and requires a `MAJOR` version
bump. Follow the [upgrade guide](upgrade-guide.md) and remove the identifier
from `REQUIREMENTS.md`, this file, and every test module simultaneously.
