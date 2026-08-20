<div align="center">
  <img src="data/icons/com.eduhcommerce.PrintArchive.svg" width="120" alt="PyCUPS CUPS Archive icon">
  <h1>PyCUPS</h1>
  <p><strong>Your local CUPS print history, ready to preview, export, and reprint.</strong></p>
  <p>A privacy-first GTK 4 and Libadwaita desktop application for retained print jobs on Linux.</p>
  <p>
    <a href="README.pt-BR.md">Português (Brasil)</a>
    ·
    <a href="https://github.com/ehstbr/PyCUPS/releases/latest">Latest release</a>
    ·
    <a href="https://github.com/ehstbr/PyCUPS/issues">Report an issue</a>
    ·
    <a href="CHANGELOG.md">Changelog</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/version-0.1.11-e95420?style=flat-square" alt="PyCUPS version 0.1.11">
    <img src="https://github.com/ehstbr/PyCUPS/actions/workflows/ci.yml/badge.svg" alt="PyCUPS continuous integration status">
    <img src="https://img.shields.io/badge/platform-Linux-f0c674?style=flat-square&logo=linux&logoColor=111" alt="Linux">
    <img src="https://img.shields.io/badge/desktop-GNOME-4a86cf?style=flat-square&logo=gnome&logoColor=white" alt="GNOME desktop">
    <img src="https://img.shields.io/badge/GTK-4-4a86cf?style=flat-square&logo=gtk&logoColor=white" alt="GTK 4">
    <img src="https://img.shields.io/badge/printing-CUPS-6b7280?style=flat-square" alt="CUPS printing">
    <img src="https://img.shields.io/badge/license-GPLv3%2B-2da44e?style=flat-square" alt="GNU GPL version 3 or later">
  </p>
</div>

<p align="center">
  <img src="docs/screenshots/main-window.png" width="940" alt="PyCUPS Linux CUPS print history browser with retained document preview">
</p>

## A native CUPS print archive for the Linux desktop

**PyCUPS — CUPS Archive** turns the print jobs already retained by your local
CUPS service into a practical desktop history. Search past jobs, inspect their
metadata, preview preserved documents, export an original file, restart the
exact job, or create a new PDF reprint with selected pages.

It is designed for Ubuntu and other Debian-based GNOME systems and stays close
to the platform: Python, GTK 4, Libadwaita, the system PyCUPS bindings, IPP,
Poppler, and PolicyKit. It does not run a cloud archive and never reads the
private CUPS spool directory directly.

> [!IMPORTANT]
> PyCUPS can only preview, export, or reprint a document while CUPS still has
> its retained spool file. Installing the application cannot restore files that
> CUPS already expired or purged.

## When PyCUPS can be useful

PyCUPS is especially helpful when you need to:

- **Reprint an invoice, receipt, shipping label, report, or form** after the
  original application or browser tab has already been closed.
- **Recover a recent print job after a paper jam, damaged sheet, wrong tray, or
  interrupted print**, provided CUPS retained the file.
- **Find who printed what and where** by searching job title, user, printer,
  state, date, or CUPS job number.
- **Export the retained source document** before it expires from the print
  service.
- **Print only selected PDF pages**, such as `1,4,7-10`, without reopening or
  recreating the original document.
- **Send an old PDF job to another printer, paper size, scale, or copy count**
  and inspect an IPP-based target-sheet preview first.
- **Restart raw or thermal-printer data exactly as CUPS received it** when the
  original retained job is still available.
- **Keep a controlled local print history in retail, logistics, dispatch,
  administration, schools, labs, service desks, and small offices** without
  uploading documents to a third party.
- **Balance recovery and privacy** by configuring separate retention periods
  for spool files and metadata.

## Highlights

| Area | What PyCUPS provides |
| --- | --- |
| History | Live CUPS job list, search, state filters, and all/one/multiple-printer selection |
| Preview | PDF pages, common images, and text; zoom, mouse-wheel zoom, 100%, fit-to-window, rotation, scrollbars, and drag-to-pan |
| Reprint | Exact CUPS restart or flexible PDF reprint with page ranges, destination, paper, scaling, and copies |
| Export | Save the original retained document through the authorized CUPS API |
| Retention | Editable file/history/`MaxJobs` values with explicit PolicyKit authorization |
| Server | A small, bounded set of global CUPS switches—never a printer or driver editor |
| Safety | Confirmation before destructive actions and a blocking readiness check after CUPS restarts |
| Privacy | Local documents, no telemetry, no analytics, no cloud archive, and no stored CUPS password |
| Updates | Validated GitHub manifest with optional and mandatory update flows |
| Languages | English source interface and Brazilian Portuguese translation |

## Screenshots

### Reprint a retained job with a realistic destination preview

<p align="center">
  <img src="docs/screenshots/reprint-preview.png" width="940" alt="PyCUPS reprint dialog with destination printer, paper, scaling, copies, pages, and print preview">
</p>

The reprint preview is intentionally different from the main viewer. The main
viewer may rotate and zoom a page for comfortable reading; the reprint dialog
shows the calculated physical result for the selected printer, paper, printable
margins, orientation, and scaling.

<details>
<summary><strong>First-run privacy and retention assistant</strong></summary>
<br>
<table>
  <tr>
    <td width="33%" align="center"><strong>Privacy first</strong><br><img src="docs/screenshots/onboarding-welcome.png" alt="PyCUPS welcome screen explaining local privacy and open-source code"></td>
    <td width="33%" align="center"><strong>Editable proposal</strong><br><img src="docs/screenshots/onboarding-retention.png" alt="PyCUPS onboarding showing current CUPS retention and editable suggested values"></td>
    <td width="33%" align="center"><strong>Clear completion</strong><br><img src="docs/screenshots/onboarding-complete.png" alt="PyCUPS onboarding completion screen"></td>
  </tr>
</table>
</details>

<details>
<summary><strong>Global CUPS settings and maintenance</strong></summary>
<br>
<table>
  <tr>
    <td width="33%" align="center"><strong>Retention</strong><br><img src="docs/screenshots/settings-retention.png" alt="PyCUPS CUPS retained file, history, and MaxJobs settings"></td>
    <td width="33%" align="center"><strong>Server</strong><br><img src="docs/screenshots/settings-server.png" alt="PyCUPS global CUPS access, sharing, and diagnostics settings"></td>
    <td width="33%" align="center"><strong>Maintenance</strong><br><img src="docs/screenshots/settings-maintenance.png" alt="PyCUPS local print service information and history maintenance tools"></td>
  </tr>
</table>
</details>

## How it works

```mermaid
flowchart LR
    A["Applications print"] --> C["Local CUPS service"]
    C --> J["Retained jobs"]
    J --> P["PyCUPS"]
    P --> R["Preview · Export · Reprint"]
```

PyCUPS requests job metadata and retained documents through PyCUPS/IPP. CUPS
remains the source of truth and controls permissions, file availability, job
retention, and exact restart behavior.

### History metadata is not the same as a retained document

| CUPS data | Lets PyCUPS show | Required for preview/export/reprint |
| --- | --- | --- |
| Job history | Name, user, printer, state, date, size, and job number | No |
| Retained spool file | The printable document kept by CUPS | Yes |

A job can therefore remain visible after its printable file expires. PyCUPS
shows that distinction instead of promising recovery when only metadata exists.

## Installation

### Debian package — recommended

Download the `.deb` from the
[latest release](https://github.com/ehstbr/PyCUPS/releases/latest), then install
it with APT so system dependencies are resolved automatically:

```bash
cd ~/Downloads
sudo apt update
sudo apt install ./print-archive_0.1.11_all.deb
```

Open **PyCUPS** from the application grid or run:

```bash
print-archive
```

The internal Debian package and command retain the historical name
`print-archive` so upgrades from earlier releases preserve the installed app,
preferences, and launcher identity.

### Source ZIP

Install the runtime dependencies first:

```bash
sudo apt update
sudo apt install \
  python3 python3-gi python3-cups python3-pypdf \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 \
  gir1.2-soup-3.0 poppler-utils cups-client cups-daemon \
  pkexec gettext
```

Then extract and run the GitHub source package:

```bash
unzip PyCUPS-0.1.11.zip
cd PyCUPS-0.1.11
./run.sh
```

`run.sh` uses the distribution's Python and GI packages. It does not create a
virtual environment or download dependencies from the internet.

## First launch and suggested CUPS retention

The three-step welcome flow explains privacy, reads the live CUPS values, and
offers an editable starting point:

| CUPS directive | Suggested value | Purpose |
| --- | ---: | --- |
| `PreserveJobFiles` | `2592000` | Keep reprintable spool files for 30 days |
| `PreserveJobHistory` | `7776000` | Keep job metadata for 90 days |
| `MaxJobs` | `0` | Avoid a job-count cap shortening either time period |

These values are **never applied by installation, update, startup, or simple
navigation**. The user must press **Apply and continue** and authorize the
change through PolicyKit. **Skip without changes** preserves the existing CUPS
configuration exactly.

Only an onboarding-completed flag is saved under the user's XDG configuration
directory, normally `~/.config/pycups/state.json`. It contains no document,
job metadata, CUPS value, username, or password.

After retention or server settings are saved, the whole application stays
blocked behind **Restarting CUPS…**. PyCUPS creates fresh IPP connections and
requires consecutive successful probes before it releases the interface and
reloads history. The background action buttons keep their normal labels; the
modal dialog is the single source of progress information.

## Preview controls

The main document viewer supports:

- zoom out and zoom in buttons;
- an editable zoom-percentage control from 1% to 500%;
- mouse-wheel zoom while the pointer is over the preview;
- fit-to-window and actual 100% size;
- visual rotation left or right in 90-degree steps;
- scrollbars and drag-to-pan when the page is larger than the viewport.

Rotation changes only the on-screen view. It never modifies the retained file
or the physical orientation of a reprint.

## Exact restart versus flexible PDF reprint

- **Exact restart:** CUPS restarts every page, one copy, on the original
  printer while reusing retained print attributes.
- **Flexible reprint:** PyCUPS creates a new job for selected PDF pages,
  another printer, paper, scale, or copy count.
- **Target-sheet preview:** PyCUPS composes an approximation from IPP media
  dimensions, printable margins, and `print-scaling`. A driver or printer can
  still apply hardware-specific transformations.
- **Raw and thermal formats:** when retained, they may be restarted exactly but
  are not rendered or split into pages.
- **Multiple documents:** all-PDF jobs are combined in document order. Mixed
  formats remain limited to exact restart.

Example for a ten-page retained PDF:

1. Select the job and wait for its preview.
2. Choose **Reprint**.
3. Turn off **Restart the original job exactly** and **Print all pages**.
4. Enter `4` for one page or `1,4,7-10` for six pages.
5. Choose destination, paper, scale, and copies; inspect the preview and press
   **Print**.

Generated page subsets and preview images live in a private per-process
temporary directory (`0700`); files use mode `0600`, and everything is removed
when PyCUPS exits.

## Permissions, security, and privacy

- Retained documents and job metadata stay on the computer running CUPS.
- There is no telemetry, advertising, analytics, cloud archive, or automatic
  crash upload.
- The only automatic internet request reads the small `version.json` manifest
  from this GitHub repository.
- PyCUPS uses authorized CUPS operations instead of weakening permissions on
  `/var/spool/cups`.
- If CUPS requests a username and password, the password is cleared after the
  request and is never persisted by PyCUPS.
- Global retention and server changes pass through the bounded, root-owned
  `/usr/lib/print-archive/apply-settings` helper and a native PolicyKit prompt.
- Individual and complete-history deletion always require explicit
  confirmation.

Print files may contain confidential information. Longer retention and
`MaxJobs=0` can also consume significant disk space on busy computers. Choose
values appropriate for the machine and monitor the CUPS spool filesystem.

## Compatibility and limitations

- Designed for Ubuntu 24.04 or later and comparable Debian-based GNOME systems
  with Python 3.12, GTK 4, Libadwaita 1.5, CUPS, and PolicyKit.
- PDF preview requires `pdftoppm` from `poppler-utils`.
- Encrypted, malformed, or unsupported files may not be previewable.
- Permissions depend on the local CUPS policy and the job owner.
- PyCUPS manages a bounded set of **global** CUPS values; it intentionally does
  not add printers, install drivers, edit queues, or change per-printer options.
- The product is separate from—but built on—the system Python bindings commonly
  called **PyCUPS**.

## Translations

- [Read this documentation in Portuguese (Brazil)](README.pt-BR.md)
- [Brazilian Portuguese interface catalog](po/pt_BR.po)
- [Translation template for new languages](po/print-archive.pot)
- [How to contribute a translation](CONTRIBUTING.md#translations)

English is the source language. New translations are welcome when their
catalog remains complete and format placeholders are preserved.

## Development and tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
meson setup build
meson compile -C build
```

The pure-Python core does not import GTK. Page ranges, PDF transformations,
CUPS normalization, retention validation, temporary-file isolation, semantic
version checks, and preview geometry are covered independently from the UI.

Focused contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md)
and preserve the project's local-first privacy model and deliberately narrow
CUPS scope. For questions, see [SUPPORT.md](SUPPORT.md); please report sensitive
problems through the private process in [SECURITY.md](SECURITY.md).

## License

Copyright © 2026 EduhCommerce.

PyCUPS is free and open-source software licensed under the
[GNU General Public License version 3 or later](LICENSE).
