from __future__ import annotations

import platform
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from .. import APP_ID, APP_NAME, APP_TAGLINE, VERSION
from ..util.i18n import _
from .about_content import release_notes_markup


WEBSITE_URL = "https://eduhcommerce.com.br"
PROJECT_URL = "https://github.com/ehstbr/PyCUPS"
ISSUES_URL = f"{PROJECT_URL}/issues"
CHANGELOG_URL = f"{PROJECT_URL}/blob/main/CHANGELOG.md"
THIRD_PARTY_URL = f"{PROJECT_URL}/blob/main/THIRD-PARTY.md"
CHECK_UPDATES_URI = "print-archive://check-update"


def show_about_dialog(
    parent: Gtk.Window,
    check_for_updates: Callable[[Gtk.Window | None], None] | None = None,
    service: object | None = None,
) -> None:
    about = Adw.AboutDialog(
        application_name=APP_NAME,
        application_icon=APP_ID,
        version=VERSION,
        developer_name="EduhCommerce",
        comments=_(
            "{tagline} — View, preview, reprint, export, and administer retained CUPS jobs."
        ).format(tagline=APP_TAGLINE),
        website=WEBSITE_URL,
        issue_url=ISSUES_URL,
        copyright="© 2026 EduhCommerce",
    )
    about.set_license_type(Gtk.License.GPL_3_0)
    about.set_release_notes(release_notes_markup())
    if hasattr(about, "set_release_notes_version"):
        about.set_release_notes_version(VERSION)

    about.add_link(_("Source code on GitHub"), PROJECT_URL)
    if check_for_updates:
        about.add_link(_("Check for Updates"), CHECK_UPDATES_URI)

        def activate_link(_dialog: Adw.AboutDialog, uri: str) -> bool:
            if uri != CHECK_UPDATES_URI:
                return False
            about.close()
            GLib.idle_add(lambda: check_for_updates(parent))
            return True

        about.connect("activate-link", activate_link)
    about.add_link(_("Report a problem"), ISSUES_URL)
    about.add_link(_("Complete changelog"), CHANGELOG_URL)
    about.add_link(_("Third-party projects and licenses"), THIRD_PARTY_URL)

    about.add_acknowledgement_section(
        _("Printing Technologies"),
        ["OpenPrinting CUPS", "PyCUPS Python bindings", "PWG IPP", "Poppler"],
    )
    about.add_acknowledgement_section(
        _("Desktop Technologies"),
        ["GTK 4", "Libadwaita", "GLib", "PolicyKit"],
    )
    about.add_acknowledgement_section(_("Document Processing"), ["pypdf"])
    about.add_acknowledgement_section(
        _("Languages"), ["English", "Português (Brasil)"]
    )

    if hasattr(about, "set_debug_info"):
        debug = [
            f"{APP_NAME}: {VERSION}",
            f"Python: {platform.python_version()}",
            f"GTK: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
            f"Libadwaita: {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}",
            f"Platform: {platform.platform()}",
        ]
        if service is not None:
            cups_module = getattr(service, "cups", None)
            get_server = getattr(cups_module, "getServer", None)
            get_user = getattr(cups_module, "getUser", None)
            debug.extend(
                (
                    f"CUPS server: {get_server() if callable(get_server) else 'unknown'}",
                    f"CUPS user: {get_user() if callable(get_user) else 'unknown'}",
                    f"PyCUPS: {getattr(cups_module, '__version__', 'system package')}",
                )
            )
        about.set_debug_info("\n".join(debug))
        about.set_debug_info_filename("pycups-debug.txt")
    about.present(parent)
