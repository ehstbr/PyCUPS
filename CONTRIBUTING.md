# Contributing

PyCUPS welcomes focused changes that preserve its small, native GNOME
design and privacy model.

## Development setup

On Ubuntu 24.04 or later, install the dependencies listed in `README.md`, then
run:

```bash
./tools/run-tests.sh
./run.sh
```

The CUPS and PDF logic belongs under `src/print_archive/core` and must remain
usable without importing GTK. UI code belongs under `src/print_archive/ui`.

## Safety requirements

- Never read `/var/spool/cups` directly or weaken its filesystem permissions.
- Never persist spool documents outside the explicitly requested export path.
- Never store an administrator password.
- Keep privileged operations in the bounded `apply-settings` helper.
- Keep server settings global; do not turn this project into a per-printer,
  driver, or queue administration interface.
- Keep the update manifest bounded, SemVer-validated, UTC-dated, and fail-open
  for network errors; mandatory releases must block use of the old version.
- Confirm destructive job purges in the interface.
- Add regression tests for page-range parsing and PDF transformation changes.

Run the complete test suite before submitting a change and keep English source
messages plus `pt_BR` translations synchronized.
