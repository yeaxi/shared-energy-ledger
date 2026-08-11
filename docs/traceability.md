# Traceability matrix

Each invariant from [`REQUIREMENTS.md#a3`](https://github.com/yeaxi/energy-split-dashboard/blob/main/REQUIREMENTS.md#a3-non-functional-invariants)
is covered by at least one test module under `tests/`. The mapping
below is enforced by
[`scripts/check_requirements_traceability.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/scripts/check_requirements_traceability.py),
which fails CI when an invariant identifier is not referenced by any
file under `tests/`.

## Mapping

| Invariant | Description (short) | Test modules |
| --- | --- | --- |
| `I1` | No silent zero. | [`tests/unit/test_tariff.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_tariff.py), [`tests/unit/test_allocation.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_allocation.py), [`tests/unit/test_ledger.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_ledger.py), [`tests/unit/test_samples.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_samples.py), [`tests/unit/test_report.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_report.py) |
| `I2` | Per-data-class freshness. | [`tests/unit/test_samples.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_samples.py) |
| `I3` | Closed allocation enum. | [`tests/unit/test_allocation.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_allocation.py) |
| `I4` | Residual fallback rules. | [`tests/unit/test_allocation.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_allocation.py) |
| `I5` | Recorder unit metadata is validated. | [`tests/unit/test_samples.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_samples.py) |
| `I6` | Battery ledger safety. | [`tests/unit/test_ledger.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_ledger.py) |
| `I7` | Report v2 contract. | [`tests/unit/test_report.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_report.py), [`tests/unit/test_tariff.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_tariff.py) |
| `I8` | Report v2 contract. | [`tests/unit/test_report.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_report.py) |
| `I9` | Config-entry migration. | [`tests/unit/test_tariff.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_tariff.py) |
| `I10` | Dashboards fail closed. | [`tests/unit/test_report.py`](https://github.com/yeaxi/energy-split-dashboard/blob/main/tests/unit/test_report.py) |

`I8` and `I10` are additionally covered by the frontend card contract
tests when the companion card bundle is checked in; those tests are
kept in the `dashboard/` package.

## Adding a new invariant

When a new invariant is added:

1. Update [`REQUIREMENTS.md`](https://github.com/yeaxi/energy-split-dashboard/blob/main/REQUIREMENTS.md)
   with the new identifier (`I11`, `I12`, ...).
2. Add or extend a test module under `tests/` that references the new
   identifier at least once.
3. Add the invariant to [invariants.md](invariants.md) with the
   verbatim wording and a plain-language note.
4. Extend the table above with the covering test modules.
5. Rerun `python scripts/check_requirements_traceability.py` locally
   to confirm CI will pass.

## Retiring an invariant

Retiring an invariant is a **breaking change** and requires a `MAJOR`
version bump. Follow the [upgrade guide](upgrade-guide.md) and remove
the identifier from `REQUIREMENTS.md`, this file, and every test
module simultaneously.
