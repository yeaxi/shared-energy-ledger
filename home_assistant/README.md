# Home Assistant artifacts

`packages/energy_split.yaml` is the local candidate package. The three JSON files under `lovelace/` are storage/registry/resource snapshots; they are not direct drop-in instructions for editing `.storage` without a backup and approval.

The package is expected to be included by the existing Home Assistant `/config/packages/` include. The active dashboard is registered as `energy_split` at `/energy-split`.

Before deployment, compare the candidate to a fresh live snapshot. Do not deploy an old snapshot over a newer live package.
