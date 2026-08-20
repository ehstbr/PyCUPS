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

## Translations

English strings in the Python source are the translation source. The template
is stored in [`po/print-archive.pot`](po/print-archive.pot), and every supported
locale is listed in [`po/LINGUAS`](po/LINGUAS).

To add or update a language:

1. Copy or merge the POT template into `po/<locale>.po`.
2. Preserve Python brace placeholders such as `{app_name}` and `{count}`.
3. Add a new locale code to `po/LINGUAS` and to
   `tools/compile-translations.sh` when required.
4. Run `msgfmt --check --check-format` for every edited catalog.
5. Keep the translated catalog complete—without fuzzy or empty messages—before
   proposing it as an officially supported language.

The current Brazilian Portuguese catalog is available at
[`po/pt_BR.po`](po/pt_BR.po). Documentation translations should link back to
the English [`README.md`](README.md), and the English README must link to every
complete documentation translation.

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
