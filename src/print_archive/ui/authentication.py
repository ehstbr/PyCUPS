from __future__ import annotations

import threading
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from ..util.i18n import _


@dataclass(slots=True)
class _CredentialRequest:
    prompt: str
    current_user: str
    method: str
    resource: str
    completed: threading.Event
    credentials: tuple[str, str] | None = None


class CupsAuthenticationDialog:
    """Bridge a blocking PyCUPS callback to a native GTK dialog."""

    def __init__(self, parent: Gtk.Window) -> None:
        self.parent = parent
        self._prompt_lock = threading.Lock()

    def request_credentials(
        self,
        prompt: str,
        current_user: str,
        method: str,
        resource: str,
    ) -> tuple[str, str] | None:
        request = _CredentialRequest(
            prompt=prompt,
            current_user=current_user,
            method=method,
            resource=resource,
            completed=threading.Event(),
        )
        # If two background tasks are challenged, show one credential dialog at
        # a time. This method never runs on GTK's main thread.
        with self._prompt_lock:
            GLib.idle_add(self._show_request, request)
            request.completed.wait()
        return request.credentials

    def _show_request(self, request: _CredentialRequest) -> bool:
        dialog = Adw.AlertDialog(
            heading=_("Authenticate with CUPS"),
            body=_(
                "CUPS requires the job owner or a printing administrator to access "
                "or reprint this document. The password is not saved."
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("authenticate", _("Authenticate"))
        dialog.set_response_appearance(
            "authenticate", Adw.ResponseAppearance.SUGGESTED
        )
        dialog.set_default_response("authenticate")
        dialog.set_close_response("cancel")

        form = Gtk.Grid(row_spacing=8, column_spacing=12)
        form.set_margin_top(6)
        username_label = Gtk.Label(label=_("Username"), xalign=0)
        username_entry = Gtk.Entry(
            text=request.current_user,
            hexpand=True,
            activates_default=True,
        )
        password_label = Gtk.Label(label=_("Password"), xalign=0)
        password_entry = Gtk.PasswordEntry(
            hexpand=True,
            show_peek_icon=True,
            activates_default=True,
        )
        prompt_label = Gtk.Label(
            label=request.prompt,
            xalign=0,
            wrap=True,
            selectable=True,
            css_classes=["dim-label", "caption"],
        )
        form.attach(username_label, 0, 0, 1, 1)
        form.attach(username_entry, 1, 0, 1, 1)
        form.attach(password_label, 0, 1, 1, 1)
        form.attach(password_entry, 1, 1, 1, 1)
        form.attach(prompt_label, 0, 2, 2, 1)
        dialog.set_extra_child(form)

        def update_authenticate_response(_entry: Gtk.Widget) -> None:
            dialog.set_response_enabled(
                "authenticate",
                bool(username_entry.get_text().strip() and password_entry.get_text()),
            )

        username_entry.connect("changed", update_authenticate_response)
        password_entry.connect("changed", update_authenticate_response)
        update_authenticate_response(password_entry)

        def chosen(source: Adw.AlertDialog, result: Gio.AsyncResult) -> None:
            try:
                try:
                    response = source.choose_finish(result)
                except Exception:
                    response = "cancel"
                username = username_entry.get_text().strip()
                password = password_entry.get_text()
                if response == "authenticate" and username and password:
                    request.credentials = (username, password)
            finally:
                password_entry.set_text("")
                request.completed.set()

        dialog.choose(self.parent, None, chosen)
        password_entry.grab_focus()
        return GLib.SOURCE_REMOVE
