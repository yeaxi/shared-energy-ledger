# Security policy

## Reporting a vulnerability

If you discover a vulnerability in the Shared Energy Ledger integration or its
companion cards, please **do not open a public GitHub issue**. Instead:

1. Email the maintainer team via the address listed on the repository's
   GitHub profile, or use GitHub's
   [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
   feature on this repository.
2. Include a minimal reproduction using a **synthetic** Home Assistant
   setup. Do not include personally identifying information, entity IDs from
   your own installation, or excerpts of real cost data.

We aim to acknowledge reports within seven days and to publish a fix in a
security release with credit to the reporter, subject to the reporter's
consent.

## Scope

This project is a read-only accounting layer. It does not control physical
devices and does not call side-effecting Home Assistant services. Reports
that describe hypothetical exploitation of a device-control path are out of
scope; the integration simply does not have that surface.

Reports that describe:

- leakage of personal data through diagnostics or reports,
- reintroduction of a private-installation identifier from `legacy/`,
- weakening of a documented invariant that lets a cost sensor report a
  fabricated `0`,

are in scope and treated as security bugs even when they do not lead to
remote code execution.
