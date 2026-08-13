# Shared Energy Ledger

[![CI](https://github.com/yeaxi/shared-energy-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/yeaxi/shared-energy-ledger/actions/workflows/ci.yml)
[![Docs](https://github.com/yeaxi/shared-energy-ledger/actions/workflows/docs.yml/badge.svg)](https://yeaxi.github.io/shared-energy-ledger/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A [Home Assistant](https://www.home-assistant.io/) add-on for buildings that
**share one electricity connection** between several flats or houses. It works
out **who owes how much** for any period of time, in your own currency.

> Who owes how much, for any date range?

If you have one shared grid meter (and, optionally, shared solar panels or a
shared battery) plus a meter for each home, Shared Energy Ledger keeps a fair,
per-home running cost. It only reads your meters and does the maths. It never
switches anything on or off.

## What it does

- Splits the shared bill between two or more homes, based on the meters you
  provide.
- Optionally includes shared **solar panels** and a shared **battery**, and
  prices solar energy and grid energy separately.
- Supports **day/night** (time-of-use) pricing.
- Works in **any currency**.
- Gives you accurate cost reports for any date range.
- **Never guesses.** If a meter is missing or reporting bad data, the cost
  shows as `unavailable` instead of a wrong number.

## What you need

- A working Home Assistant with [HACS](https://www.hacs.xyz/) installed.
- A grid **import** energy meter (in `kWh`) in Home Assistant.
- One energy meter per home, or a whole-building meter to split from.
- Optional: solar and/or battery meters if you have them.

## Install

1. In Home Assistant, open **HACS**.
2. Open the menu (top right) and choose **Custom repositories**.
3. Paste `https://github.com/yeaxi/shared-energy-ledger` and pick the
   **Integration** category, then click **Add**.
4. **Restart Home Assistant.**

Full step-by-step instructions with screenshots are in the
[Quickstart guide](https://yeaxi.github.io/shared-energy-ledger/quickstart/).

## Set it up

1. Go to **Settings -> Devices & services -> Add integration**.
2. Search for **Shared Energy Ledger** and follow the setup wizard. It asks
   for your currency, your grid meter, optional solar and battery, and a meter
   for each home.

Every option is explained in the
[Configuration reference](https://yeaxi.github.io/shared-energy-ledger/configuration/).
No YAML editing is required.

## Get help and report a bug

- Have a question? Check the
  [documentation](https://yeaxi.github.io/shared-energy-ledger/) and the
  [Troubleshooting guide](https://yeaxi.github.io/shared-energy-ledger/troubleshooting/)
  first.
- Found a bug? [Open a bug report](https://github.com/yeaxi/shared-energy-ledger/issues/new/choose).
  The form asks for your Home Assistant version, the integration version, what
  you expected, what happened, and the steps to reproduce it. Please remove any
  personal data before submitting.
- Found a security issue? Do not open a public issue. Follow
  [`SECURITY.md`](SECURITY.md) instead.

## Documentation

The full documentation site is at
**<https://yeaxi.github.io/shared-energy-ledger/>**. The source lives in
[`docs/`](docs/).

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the
developer setup and checks, and [`ARCHITECTURE.md`](ARCHITECTURE.md) for how
the project is put together.

## License

MIT. See [`LICENSE`](LICENSE).
