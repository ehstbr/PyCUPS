# PyCUPS

**CUPS Archive for retained print jobs.**

PyCUPS is a lightweight GTK 4 and Libadwaita desktop application for
Ubuntu and other Debian-based GNOME systems. It works with the local CUPS
service to browse job history, retrieve preserved spool documents, preview or
export them, and reprint complete jobs or selected PDF pages.

Project repository: <https://github.com/ehstbr/PyCUPS>

The project follows the conventions used by PyNextCloud Sync:
one native single-instance application, a small testable Python core, Meson
metadata, a source ZIP, a Debian package, Brazilian Portuguese localization,
and no application-specific password storage.

## Highlights

- Search the history and filter it by job state, all printers, or any
  checkbox-selected combination of printers.
- Refresh CUPS history automatically every 10 seconds so new jobs appear
  without reopening the application.
- Preview retained PDF files page by page, plus common image and text formats.
- Reprint the exact original job when using all pages, one copy, and the
  original printer.
- Reprint selected PDF pages using ranges such as `3`, `2-5`, or
  `1,4,7-10`. PyCUPS physically creates a temporary PDF containing only
  those pages before submitting a new job.
- Choose another printer, paper size, scaling mode, and copy count for flexible
  reprints, with a PDF target-sheet preview based on destination capabilities.
- Export a retrieved document without reading `/var/spool/cups` directly.
- Purge one job or all visible job history after an explicit confirmation.
- Configure retention and bounded global CUPS switches in separate Retention,
  Server, and Maintenance pages with a native PolicyKit prompt.
- Use a three-step first-run welcome flow to review privacy and compare live
  CUPS values with an editable retention suggestion.
- Check a validated GitHub manifest at startup or on demand, using the same
  optional/mandatory update behavior as PyNextCloud Sync.

## First-run welcome and privacy

The first launch presents three pages: a privacy and open-source introduction,
an editable retention proposal, and a completion summary. PyCUPS does not
upload retained documents or job metadata. Its only automatic internet request
reads the small version manifest from GitHub; print content is never included.

The proposal page reads the live CUPS configuration before enabling **Apply and
continue**. **Skip without changes** leaves every current value untouched. The
flow can be opened again from **Welcome and initial setup** in the main menu.

Only an onboarding-completed flag is stored under the user's XDG configuration
directory, normally `~/.config/pycups/state.json`. That file contains no CUPS
value, document name, job metadata, credential, or print content.

## Retention configuration is never automatic

Installing, updating, or opening PyCUPS does not change the CUPS
configuration. The settings screen first reads the values currently used by
the computer. Controls remain disabled if that read fails, preventing an
unknown configuration from being overwritten accidentally.

Changes happen only after the user edits the fields, presses **Apply**, and
authorizes the operation through PolicyKit. The first-run flow offers this
editable balance:

| CUPS directive | Value | Meaning |
|---|---:|---|
| `PreserveJobFiles` | `2592000` | Keep reprintable spool files for 30 days. |
| `PreserveJobHistory` | `7776000` | Keep job metadata for 90 days. |
| `MaxJobs` | `0` | Do not impose a job-count limit. |

After retention or global server settings are saved, PyCUPS shows a blocking
**Restarting CUPS…** dialog. It pauses history refresh, creates fresh IPP
connections until several consecutive probes succeed, and only then restores
the interface and reloads jobs. If the service remains unavailable, the dialog
continues blocking the app and starts another probe automatically. **Try
again** requests an immediate attempt, while **Close PyCUPS** provides a safe
exit if the service cannot recover.

These are suggested form values, not package or startup defaults. Their finite
time windows balance recent-print recovery with privacy; `MaxJobs=0` prevents a
count cap from shortening those windows. The documented CUPS defaults are
different: retained files are kept for
86,400 seconds (one day), history metadata is enabled without a time limit,
and `MaxJobs` is 500. A finite `MaxJobs` can therefore remove older entries
before a long time-based retention window is reached.

The Retention tab also offers **No time limit for retained files**, which sends
`PreserveJobFiles=Yes`. This remains subject to job removal by `MaxJobs`; pair
it with `MaxJobs=0` only when disk usage is monitored.

## Installation on Ubuntu

Install the supplied Debian package:

```bash
sudo apt install ./print-archive_0.1.10_all.deb
```

The package declares the required Ubuntu dependencies, including PyCUPS,
pypdf, GTK 4, Libadwaita, Poppler utilities, CUPS, and PolicyKit.

Launch **PyCUPS** from the application grid or run:

```bash
print-archive
```

To run directly from the source archive:

```bash
sudo apt install python3 python3-gi python3-cups python3-pypdf \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-soup-3.0 \
  poppler-utils cups-client cups-daemon pkexec gettext
./run.sh
```

## Selected-page behavior

Selected-page reprinting is intentionally implemented for retained PDFs.
Suppose job 42 has 10 pages:

1. Select job 42 and wait for its preview.
2. Choose **Reprint…**.
3. Turn off **Restart the original job exactly** and **Print all pages**.
4. Enter `4` to print only page 4, or `1,4,7-10` for six pages.
5. Choose the printer, target paper, scaling, and copies; inspect the preview,
   then press **Print**.

The source job stays unchanged. The generated PDF and preview images live in a
private, per-process temporary directory with mode `0700`; files use mode
`0600`, and the directory is deleted when the application exits.

## Exact restart versus flexible reprint

- **Exact restart:** enable the exact-restart switch. CUPS restarts all pages,
  one copy, on the original printer while preserving retained print attributes.
- **Flexible reprint:** selected pages, multiple copies, or another printer.
  A new job is submitted with the selected copy count, media keyword, and
  `print-scaling`. Duplex, finishing, color, and other old-job attributes are
  not cloned.
- **Target-sheet preview:** for PDFs, PyCUPS composes an approximation
  from the IPP paper dimensions, printable margins, and scaling. The driver can
  still apply hardware-specific transformations or finishing.
- **Raw/thermal formats:** the exact job can be restarted when CUPS preserved
  it, but PyCUPS does not render or split raw printer data.
- **Multiple documents:** all-PDF jobs are combined for preview and page
  selection. Jobs containing mixed formats can only use an exact restart.

## Permissions and privacy

PyCUPS uses the system PyCUPS Python bindings and IPP operations rather than
accessing CUPS's private spool directory. CUPS may limit document retrieval,
reprinting, or deletion to the job owner or a print administrator according to
the server policy. When
CUPS challenges one of those operations, PyCUPS asks for the Ubuntu/CUPS
username and password, passes them to the thread-local PyCUPS callback, clears
the password field, and never saves the credential.

Changing retention or global CUPS switches uses the installed, root-owned
helper `/usr/lib/print-archive/apply-settings`. It accepts only three bounded
retention values or six explicit yes/no switches and invokes `cupsctl`;
PolicyKit requests administrator authorization.
The retention-settings password remains inside PolicyKit and is never received
or stored by the application.

Print files can contain confidential information. Retaining files for 30 days,
history for 90 days, and removing the `MaxJobs` cap can still use substantial
disk space on busy systems. Monitor the CUPS spool filesystem and customize the
proposal when the machine has limited storage.

## Important limitations

- PyCUPS cannot recover files that CUPS already expired or purged.
- A job may remain in the metadata history after its reprintable file expires.
- PDF preview requires `pdftoppm` from `poppler-utils`.
- Encrypted or malformed PDFs may be unavailable for preview and page splitting.
- Version 0.1.10 targets the local Ubuntu CUPS service. Settings are global to
  that service; the app intentionally does not manage individual printers.
- Target-paper preview depends on accurate IPP capabilities and cannot predict
  every driver- or hardware-specific adjustment.

## Development and tests

```bash
./tools/run-tests.sh
meson setup build
meson compile -C build
```

The core does not import GTK, allowing page-range, PDF extraction, CUPS
normalization, settings validation, and cleanup behavior to be tested with fake
connections.

## License

Copyright © 2026 EduhCommerce. Licensed under GNU GPL version 3 or later.
