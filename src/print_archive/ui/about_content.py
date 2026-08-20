from __future__ import annotations

from html import escape

from ..util.i18n import _


def release_notes_markup() -> str:
    sections = [
        (
            _("Version 0.1.12"),
            [
                _("Automatic update notices now wait until the main window is mapped and active."),
                _("The desktop compositor can now center the startup update window over PyCUPS reliably."),
                _("Manual update checks keep their existing centered behavior."),
            ],
        ),
        (
            _("Version 0.1.11"),
            [
                _("The main preview now supports zoom controls, mouse-wheel zoom, and drag-to-pan."),
                _("Pages can be rotated visually without changing the retained file or reprint orientation."),
                _("Primary actions now use symbolic icons and concise labels."),
                _("Apply and onboarding completion labels stay stable while CUPS restarts."),
                _("The GitHub source package now includes bilingual documentation and a complete screenshot gallery."),
            ],
        ),
        (
            _("Version 0.1.10"),
            [
                _("A blocking progress dialog now waits for CUPS after global settings are saved."),
                _("Fresh IPP connections must answer consistently before PyCUPS resumes."),
                _("History refresh is paused so a scheduler restart cannot appear as an application error."),
                _("If CUPS stays unavailable, PyCUPS keeps retrying automatically while the app remains blocked."),
            ],
        ),
        (
            _("Version 0.1.9"),
            [
                _("Welcome and completion headers no longer create isolated internal scrollbars."),
                _("More compact spacing keeps onboarding information visible in the standard window size."),
                _("The longer retention form uses only one page-level scrolling fallback when needed."),
            ],
        ),
        (
            _("Version 0.1.8"),
            [
                _("A three-step welcome flow explains privacy, updates, and open-source access."),
                _("Current CUPS retention values are shown beside an editable 30/90-day suggestion."),
                _("The suggested job-count limit is unlimited so time-based retention is not shortened."),
                _("Applying remains explicit and protected by administrator authorization; skipping changes nothing."),
                _("The welcome setup can be reopened from the main menu."),
            ],
        ),
        (
            _("Version 0.1.7"),
            [
                _("PyCUPS is now the consistent application name throughout the interface."),
                _("CUPS Archive is retained as the product description."),
                _("Technical identifiers remain compatible with previous installations."),
            ],
        ),
        (
            _("Version 0.1.6"),
            [
                _("Apply stays fixed below the scrolling Retention and Server forms."),
                _("Retained print files can now be kept without a time limit."),
                _("The reprint preview is displayed on the left of its options."),
                _("Per-job spool isolation fixes cached multi-page preview navigation."),
            ],
        ),
        (
            _("Version 0.1.5"),
            [
                _("Long destination-paper names no longer compress the Target paper row."),
                _("The selected paper uses an ellipsis while the popup keeps the complete names."),
                _("The complete selected paper name remains available in a tooltip."),
            ],
        ),
        (
            _("Version 0.1.4"),
            [
                _("The print history is visible immediately after the first CUPS load."),
                _("Printer selection is populated before GTK evaluates job-row visibility."),
                _("The list filter is explicitly refreshed after every history rebuild."),
            ],
        ),
        (
            _("Version 0.1.3"),
            [
                _("Filter history with checkboxes for all printers or any selected combination."),
                _("Preview a PDF reprint on the destination paper with fit, fill, actual-size, and automatic scaling."),
                _("Choose paper sizes and scaling advertised by the destination through CUPS IPP attributes."),
                _("Check GitHub for validated optional or mandatory updates at startup and on demand."),
                _("Use tabbed Retention, Server, and Maintenance settings for global CUPS configuration."),
                _("Expanded About information, project links, credits, release notes, and diagnostic details."),
            ],
        ),
        (
            _("Version 0.1.2"),
            [
                _("Added on-demand CUPS authentication for protected retained files and exact restarts."),
                _("Attempted direct retained-file retrieval even when job-preserved was not reported."),
                _("Added the first printer filter and completed Brazilian Portuguese installation support."),
            ],
        ),
        (
            _("Version 0.1.1"),
            [
                _("Loaded retention controls from the live CUPS configuration."),
                _("Kept installation and application startup free of automatic CUPS changes."),
            ],
        ),
        (
            _("Version 0.1.0"),
            [
                _("Initial release for viewing, exporting, deleting, and reprinting retained CUPS jobs."),
                _("Added selected-page extraction for retained PDF documents."),
            ],
        ),
    ]
    parts: list[str] = []
    for heading, entries in sections:
        parts.append(f"<p>{escape(heading)}</p><ul>")
        parts.extend(f"<li>{escape(item)}</li>" for item in entries)
        parts.append("</ul>")
    return "".join(parts)
