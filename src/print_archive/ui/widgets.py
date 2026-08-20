from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def button_content(label: str, icon_name: str) -> Gtk.Widget:
    content = Gtk.Box(
        spacing=6,
        halign=Gtk.Align.CENTER,
        valign=Gtk.Align.CENTER,
    )
    content.append(Gtk.Image(icon_name=icon_name))
    content.append(Gtk.Label(label=label))
    return content


def set_button_content(button: Gtk.Button, label: str, icon_name: str) -> None:
    """Give a GTK button a stable icon-and-label presentation."""

    button.set_child(button_content(label, icon_name))


def labeled_button(label: str, icon_name: str, **properties: object) -> Gtk.Button:
    return Gtk.Button(
        child=button_content(label, icon_name),
        **properties,
    )
