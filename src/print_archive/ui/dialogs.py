from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from ..util.i18n import _


def show_message(parent: Gtk.Window, heading: str, body: str) -> None:
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("close", _("Close"))
    dialog.set_default_response("close")

    def chosen(source: Adw.AlertDialog, result: Gio.AsyncResult) -> None:
        source.choose_finish(result)

    dialog.choose(parent, None, chosen)


def confirm(
    parent: Gtk.Window,
    heading: str,
    body: str,
    confirm_label: str,
    callback: object,
) -> None:
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("confirm", _(confirm_label))
    dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    def chosen(source: Adw.AlertDialog, result: Gio.AsyncResult) -> None:
        if source.choose_finish(result) == "confirm":
            callback()

    dialog.choose(parent, None, chosen)
