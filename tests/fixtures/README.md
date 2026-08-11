# Synthetic test fixtures

This folder contains **fully synthetic** data used by the test suite. Every
file in this folder must:

- Be either hand-authored or produced by a deterministic generator script
  under `scripts/`.
- Contain a header comment naming the scenario, the invariants it exercises,
  and the requirement identifier (from
  [`REQUIREMENTS.md#a3`](../../REQUIREMENTS.md#a3-non-functional-invariants))
  it maps to.
- Use only synthetic tenant names (`flat-1`, `house-a`, `unit-42`) and
  synthetic currencies (`EUR`, `USD`, `UAH`, `PLN`, `GBP`).
- Contain no personally identifying information, addresses, or hardware
  identifiers.

A repository-wide lint scans this folder for a `PRIVATE_INSTALL_DENYLIST` set
of substrings and fails the build if any listed identifier reappears here.

Fixtures under `tests/fixtures/` are the only source of test data the suite
accepts. Any test that fetches data from the network, the filesystem outside
this folder, or a real Home Assistant instance is a bug.
