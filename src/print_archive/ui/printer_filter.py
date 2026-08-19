from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..core.printer_selection import PrinterSelection
from ..util.i18n import _


class PrinterFilterMenu:
    """Menu button containing an all/individual printer checklist."""

    def __init__(self, on_changed: Callable[[], None]) -> None:
        self._on_changed = on_changed
        self._updating = False
        self.selection = PrinterSelection()
        self._printer_checks: dict[str, Gtk.CheckButton] = {}

        self.button = Gtk.MenuButton(
            label=_("All printers"),
            tooltip_text=_("Filter by one or more printers"),
        )
        self.button.set_direction(Gtk.ArrowType.DOWN)

        popover = Gtk.Popover()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        content.set_margin_start(10)
        content.set_margin_end(10)

        self.all_check = Gtk.CheckButton(label=_("All printers"), active=True)
        self.all_check.connect("toggled", self._all_toggled)
        content.append(self.all_check)
        content.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self.printer_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
        )
        scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            min_content_width=240,
            max_content_height=320,
            propagate_natural_height=True,
        )
        scroller.set_child(self.printer_box)
        content.append(scroller)
        popover.set_child(content)
        self.button.set_popover(popover)

    def update_printers(self, printers: list[str]) -> None:
        self.selection = self.selection.with_available(printers)
        self._updating = True
        try:
            while child := self.printer_box.get_first_child():
                self.printer_box.remove(child)
            self._printer_checks.clear()
            for printer in self.selection.available:
                check = Gtk.CheckButton(
                    label=printer,
                    active=printer in self.selection.selected,
                )
                check.connect("toggled", self._printer_toggled, printer)
                self._printer_checks[printer] = check
                self.printer_box.append(check)
            self.all_check.set_active(self.selection.all_selected)
        finally:
            self._updating = False
        self._update_label()

    def matches(self, printer: str) -> bool:
        return self.selection.matches(printer)

    def _all_toggled(self, check: Gtk.CheckButton) -> None:
        if self._updating:
            return
        self.selection = self.selection.select_all(check.get_active())
        self._updating = True
        try:
            for printer, printer_check in self._printer_checks.items():
                printer_check.set_active(printer in self.selection.selected)
        finally:
            self._updating = False
        self._changed()

    def _printer_toggled(self, check: Gtk.CheckButton, printer: str) -> None:
        if self._updating:
            return
        self.selection = self.selection.set_selected(printer, check.get_active())
        self._updating = True
        try:
            self.all_check.set_active(self.selection.all_selected)
        finally:
            self._updating = False
        self._changed()

    def _changed(self) -> None:
        self._update_label()
        self._on_changed()

    def _update_label(self) -> None:
        if self.selection.all_selected or not self.selection.available:
            label = _("All printers")
        elif self.selection.count == 0:
            label = _("No printers")
        elif self.selection.count == 1:
            label = next(iter(self.selection.selected))
        else:
            label = _("{count} printers").format(count=self.selection.count)
        self.button.set_label(label)
