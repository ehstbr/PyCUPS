# Changelog

All notable changes to PyCUPS are documented here.

## 0.1.10 — 2026-08-19

- Show a non-dismissible **Restarting CUPS…** mini dialog after saving
  retention or global server settings, including the onboarding proposal.
- Block every PyCUPS window, shortcut, and application action until the local
  scheduler is confirmed ready; only the progress dialog remains usable.
- Poll fresh IPP connections instead of treating the return of `cupsctl` as a
  readiness signal, require consecutive successful probes, and replace the
  stale pre-restart connection before resuming.
- Pause automatic job-history refresh and ignore an already-running refresh's
  transient connection failure while CUPS is restarting.
- Place the onboarding wait over its final page and enable **Start using
  PyCUPS** only after the connection is confirmed.
- If CUPS remains unavailable after a probe period, keep the app blocked and
  start another probe automatically; **Try again** remains available for an
  immediate attempt and **Close PyCUPS** provides a safe exit.
- Add tests for stable reconnection, timeout safety, shutdown cancellation,
  global UI blocking, and refresh suppression.

## 0.1.9 — 2026-08-19

- Replace the welcome and completion `Adw.StatusPage` heroes with compact GTK
  layouts so neither step creates an isolated internal scrollbar.
- Reduce onboarding margins, spacing, and hero icon size to fit the standard
  760 × 720 window comfortably without removing privacy or setup information.
- Keep a single page-level scrolling region as a fallback for the longer
  retention form and for unusually short resized windows; nested scrolling is
  no longer possible in any of the three steps.
- Add a regression contract covering the responsive hero and single-scroller
  structure.

## 0.1.8 — 2026-08-19

- Add a three-step first-run welcome flow with a privacy and transparency
  introduction, editable CUPS retention proposal, and final confirmation.
- Explain that retained documents and job metadata are never uploaded, the
  only automatic internet request is the GitHub version check, and the full
  source code is public.
- Read and display the computer's live `PreserveJobFiles`,
  `PreserveJobHistory`, and `MaxJobs` values before offering a change.
- Prefill an editable balance of 30-day retained files, 90-day history, and
  unlimited job count (`MaxJobs=0`). Finite time limits still prevent
  indefinite document and metadata retention.
- Require **Apply and continue** plus PolicyKit authorization before changing
  CUPS, or allow **Skip without changes** to preserve the configuration.
- Save only a local first-run completion flag under the user's configuration
  directory; no retention value or print information is stored there.
- Add **Welcome and initial setup** to the main menu so the flow can be opened
  again at any time.
- Keep mandatory updates ahead of onboarding and defer optional notices until
  the welcome flow is complete, avoiding competing startup windows.
- Add tests for the suggested profile, state-file handling, explicit-only
  application, three-page structure, and menu integration.

## 0.1.7 — 2026-08-19

- Standardize **PyCUPS** as the application name in the title bar, launcher,
  Settings, About, update messages, package metadata, and documentation.
- Retain **CUPS Archive** as the product description without restoring a
  subtitle to the main title bar.
- Distinguish the application from the system's PyCUPS Python bindings in
  credits and technical documentation.
- Keep the existing application ID, command, Debian package name, preferences,
  and update endpoint so upgrades remain compatible.

## 0.1.6 — 2026-08-19

- Move **Apply** into a fixed footer on the Retention and Server tabs so it
  remains available while their forms scroll.
- Remove the redundant loaded-configuration cards and keep concise loading or
  error feedback in the fixed footer.
- Put the reprint preview on the left and keep the options in a stable right
  pane.
- Add **No time limit for retained files**, mapped explicitly to
  `PreserveJobFiles=Yes`; installation and startup remain non-mutating.
- Namespace retrieved spool copies by job ID, preventing a newly opened job
  from overwriting the cached document of another job.
- Fix page-two preview failures and the related risk of exporting or
  reprinting the wrong cached spool copy.
- Add regression tests for fixed actions, pane order, unlimited file
  retention, and per-job spool isolation.

## 0.1.5 — 2026-08-19

- Keep the **Target paper** selector at a stable visual width so unusually
  long CUPS media names cannot compress the row title and subtitle.
- Ellipsize only the selected value while retaining complete names in the
  popup list.
- Expose the complete selected paper name through a tooltip.
- Add regression coverage for the bounded selector layout contract.

## 0.1.4 — 2026-08-19

- Fix the blank history pane shown at startup while a selected job preview was
  already visible.
- Populate the all/multiple-printer checklist before GTK evaluates each new job
  row, avoiding an initial internal state with no selected printers.
- Explicitly invalidate the `Gtk.ListBox` filter after rebuilding history so
  cached visibility cannot survive a printer-selection update.
- Preserve synchronization between the visible row and the selected job preview.

## 0.1.3 — 2026-08-19

- Replace the single-printer history selector with a checklist supporting all
  printers or any selected combination.
- Refresh the live CUPS job list every 10 seconds so newly printed and active
  jobs appear automatically.
- Read destination media, printable margins, model, defaults, and scaling
  capabilities through IPP printer attributes.
- Add a two-pane reprint dialog with exact-restart mode, destination paper and
  `print-scaling` choices, selected-page navigation, and a composed PDF
  target-sheet preview.
- Send the selected `media`, `print-scaling`, and copy count to CUPS for new
  flexible reprint jobs while preserving exact restart behavior separately.
- Add the PyNextCloud Sync update workflow: bounded and validated SemVer
  manifest, startup/manual checks, fail-open network errors, optional notices,
  blocking mandatory notices, mapped-window presentation, and GitHub release
  links.
- Expand About with release notes, GitHub, issue, changelog, license, credits,
  and diagnostic information.
- Split Settings into Retention, Server, and Maintenance pages and add only
  bounded global CUPS switches—never per-printer management.
- Extend the PolicyKit helper with explicit retention/server modes and strict
  values while keeping package installation and startup non-mutating.
- Add regression tests for printer selection, IPP capability normalization,
  PDF target-sheet composition, flexible CUPS options, global settings, and
  version-manifest validation.

## 0.1.2 — 2026-08-19

- Add a main-window printer selector with **All printers** and one entry for
  every printer found in the CUPS history.
- Register the PyCUPS password callback in the worker thread and show a native
  username/password prompt only after CUPS requests authentication.
- Clear the password field after every prompt and never persist CUPS
  credentials.
- Attempt `CUPS-Get-Document` for every eligible job, including jobs whose
  `job-preserved` attribute is false.
- Allow exact restart attempts for completed, canceled, and aborted jobs, then
  show the actual CUPS result instead of disabling the action from metadata.
- Distinguish authentication cancellation, authorization denial, missing spool
  files, and other CUPS retrieval failures.
- Fix discovery of `/usr/share/locale` so the installed package follows the
  desktop's Brazilian Portuguese locale.
- Serialize operations on the shared PyCUPS connection and add authentication
  regression tests.

## 0.1.1 — 2026-08-19

- Make explicit that installing or opening PyCUPS never changes CUPS.
- Disable retention controls until the current live CUPS values are loaded.
- Populate the editor from the computer's configuration instead of a 90-day,
  unlimited-history, and unlimited-`MaxJobs` preset.
- Remove the suggested-profile shortcut from the settings screen.
- Keep every supported value, including 90 days and `MaxJobs=0`, available for
  manual selection followed by an explicit **Apply** action.
- Add a regression test that rejects retention commands in Debian installation
  and removal scripts.

## 0.1.0 — 2026-08-19

- Add a native GTK 4 and Libadwaita history browser for local CUPS jobs.
- Search by title, user, printer, state, or job number and filter by state.
- Retrieve preserved documents through PyCUPS `getDocument`.
- Preview PDF files page by page, plus common image and text documents.
- Export a retained source document.
- Restart an exact original job through CUPS.
- Extract and reprint selected PDF pages, including ranges such as
  `1,4,7-10`, as a new job.
- Support PDF-only multi-document jobs by combining them in document order.
- Choose the destination printer and copy count for flexible reprints.
- Purge individual jobs or the complete visible history after confirmation.
- Configure 90-day file retention, time-unlimited history, and unlimited
  `MaxJobs` through a bounded PolicyKit helper.
- Document the CUPS defaults and the difference between history metadata and
  retained reprintable files.
- Add Brazilian Portuguese localization, Debian packaging, and unit tests.
