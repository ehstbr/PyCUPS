from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango

from ..core.page_ranges import PageRangeError, PageSelection, all_pages, parse_page_range
from ..models import MediaOption, PreparedJob, PrinterCapabilities, ReprintResult
from ..util.async_runner import AsyncRunner
from ..util.i18n import _
from .dialogs import show_message


_SCALING_LABELS = {
    "auto": "Automatic",
    "auto-fit": "Automatic fit",
    "fit": "Fit to printable area",
    "fill": "Fill printable area",
    "none": "Actual size",
}

_MEDIA_SELECTOR_WIDTH_CHARS = 24


def _setup_bounded_dropdown_item(
    _factory: Gtk.SignalListItemFactory,
    list_item: Gtk.ListItem,
    width_chars: int,
) -> None:
    list_item.set_child(
        Gtk.Label(
            xalign=0,
            width_chars=width_chars,
            max_width_chars=width_chars,
            ellipsize=Pango.EllipsizeMode.END,
            single_line_mode=True,
        )
    )


def _bind_bounded_dropdown_item(
    _factory: Gtk.SignalListItemFactory,
    list_item: Gtk.ListItem,
) -> None:
    label = list_item.get_child()
    item = list_item.get_item()
    if not isinstance(label, Gtk.Label):
        return
    text = item.get_string() if item is not None else ""
    label.set_label(text)
    label.set_tooltip_text(text or None)


def _bound_dropdown_selection(dropdown: Gtk.DropDown, width_chars: int) -> None:
    """Keep the selected value compact without shortening the popup list."""
    popup_factory = dropdown.get_list_factory() or dropdown.get_factory()
    selected_factory = Gtk.SignalListItemFactory()
    selected_factory.connect("setup", _setup_bounded_dropdown_item, width_chars)
    selected_factory.connect("bind", _bind_bounded_dropdown_item)
    dropdown.set_factory(selected_factory)
    if popup_factory is not None:
        dropdown.set_list_factory(popup_factory)


def _scaling_label(value: str) -> str:
    markers = {
        "auto": _("Automatic"),
        "auto-fit": _("Automatic fit"),
        "fit": _("Fit to printable area"),
        "fill": _("Fill printable area"),
        "none": _("Actual size"),
    }
    return markers.get(value, _SCALING_LABELS.get(value, value))


class ReprintDialog(Adw.Dialog):
    def __init__(
        self,
        prepared: PreparedJob,
        printers: list[str],
        capabilities: dict[str, PrinterCapabilities],
        service: object,
        runner: AsyncRunner,
        on_complete: Callable[[ReprintResult], object],
    ) -> None:
        super().__init__(title=_("Reprint"), content_width=980, content_height=680)
        self.prepared = prepared
        self.printers = printers
        self.capabilities = capabilities
        self.service = service
        self.runner = runner
        self.on_complete = on_complete
        self._media_options: list[MediaOption] = []
        self._scaling_values: list[str] = []
        self._preview_pages: tuple[int, ...] = ()
        self._preview_position = 0
        self._preview_generation = 0
        self._preview_timeout: int | None = None
        self._updating_controls = False
        self._flexible_supported = bool(
            prepared.printable_path and prepared.preview_kind not in {"raw", "multiple"}
        )

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        self.print_button = Gtk.Button(label=_("Print"), css_classes=["suggested-action"])
        self.print_button.connect("clicked", self._print)
        header.pack_end(self.print_button)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True)
        paned.set_position(530)
        paned.set_resize_start_child(True)
        paned.set_shrink_start_child(False)
        paned.set_resize_end_child(False)
        paned.set_shrink_end_child(False)
        paned.set_start_child(self._build_preview())
        paned.set_end_child(self._build_options())
        toolbar.set_content(paned)
        self.set_child(toolbar)

        self._select_original_printer()
        self._load_destination_options()
        self._update_mode()
        self._schedule_preview()

    def _build_options(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        mode_group = Adw.PreferencesGroup(
            title=_("Reprint mode"),
            description=_(
                "Exact restart asks CUPS to reuse the retained job and its original options. "
                "Turn it off to choose another printer, paper, scale, copies, or pages."
            ),
        )
        self.exact_row = Adw.SwitchRow(
            title=_("Restart the original job exactly"),
            subtitle=_("Available only for the original printer, all pages, and one copy."),
            active=True,
            sensitive=self._flexible_supported,
        )
        self.exact_row.connect("notify::active", self._exact_mode_changed)
        mode_group.add(self.exact_row)
        page.add(mode_group)

        destination_group = Adw.PreferencesGroup(title=_("Destination"))
        printer_row = Adw.ActionRow(title=_("Printer"))
        self.printer_dropdown = Gtk.DropDown.new_from_strings(self.printers)
        self.printer_dropdown.set_valign(Gtk.Align.CENTER)
        self.printer_dropdown.connect("notify::selected", self._printer_changed)
        printer_row.add_suffix(self.printer_dropdown)
        destination_group.add(printer_row)

        self.media_row = Adw.ActionRow(
            title=_("Target paper"),
            subtitle=_("Paper sizes reported by the selected destination."),
        )
        self.media_dropdown = Gtk.DropDown.new_from_strings([_("Printer default")])
        self.media_dropdown.set_valign(Gtk.Align.CENTER)
        _bound_dropdown_selection(self.media_dropdown, _MEDIA_SELECTOR_WIDTH_CHARS)
        self.media_dropdown.connect("notify::selected", self._options_changed)
        self.media_row.add_suffix(self.media_dropdown)
        destination_group.add(self.media_row)

        self.scaling_row = Adw.ActionRow(
            title=_("Scale"),
            subtitle=_("The same print-scaling option is sent to CUPS."),
        )
        self.scaling_dropdown = Gtk.DropDown.new_from_strings([_("Fit to printable area")])
        self.scaling_dropdown.set_valign(Gtk.Align.CENTER)
        self.scaling_dropdown.connect("notify::selected", self._options_changed)
        self.scaling_row.add_suffix(self.scaling_dropdown)
        destination_group.add(self.scaling_row)

        copies_adjustment = Gtk.Adjustment(
            value=1, lower=1, upper=999, step_increment=1, page_increment=10
        )
        self.copies_row = Adw.SpinRow(title=_("Copies"), adjustment=copies_adjustment)
        self.copies_row.connect("notify::value", self._options_changed)
        destination_group.add(self.copies_row)
        page.add(destination_group)

        pages_group = Adw.PreferencesGroup(title=_("Pages"))
        self.all_pages_row = Adw.SwitchRow(title=_("Print all pages"), active=True)
        self.all_pages_row.connect("notify::active", self._pages_mode_changed)
        pages_group.add(self.all_pages_row)

        total = self.prepared.total_pages
        subtitle = (
            _("Examples: 3, 2-5, or 1,4,7-10 · {total} pages available").format(total=total)
            if total
            else _("Page selection is available only when the retained document is a readable PDF.")
        )
        range_row = Adw.ActionRow(title=_("Page range"), subtitle=subtitle)
        self.range_entry = Gtk.Entry(
            placeholder_text=_("Example: 1,4,7-10"),
            width_chars=18,
            valign=Gtk.Align.CENTER,
            sensitive=False,
        )
        self.range_entry.connect("activate", self._print)
        self.range_entry.connect("changed", self._range_changed)
        range_row.add_suffix(self.range_entry)
        pages_group.add(range_row)
        page.add(pages_group)

        note_group = Adw.PreferencesGroup()
        note_group.add(
            Adw.ActionRow(
                title=_("Preview is an approximation"),
                subtitle=_(
                    "It uses the paper dimensions, printable margins, and scaling advertised by CUPS. "
                    "The printer driver may still apply finishing or hardware-specific adjustments."
                ),
                icon_name="dialog-information-symbolic",
            )
        )
        page.add(note_group)

        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(page)
        return scroller

    def _build_preview(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        title = Gtk.Label(label=_("Reprint preview"), xalign=0, css_classes=["title-2"])
        root.append(title)
        self.preview_description = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label"])
        root.append(self.preview_description)

        self.preview_stack = Gtk.Stack(vexpand=True, hexpand=True)
        self.preview_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading.set_valign(Gtk.Align.CENTER)
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        spinner.set_halign(Gtk.Align.CENTER)
        loading.append(spinner)
        loading.append(Gtk.Label(label=_("Composing target sheet…"), css_classes=["dim-label"]))
        self.preview_stack.add_named(loading, "loading")

        self.preview_picture = Gtk.Picture(
            can_shrink=True,
            content_fit=Gtk.ContentFit.CONTAIN,
            alternative_text=_("Target-sheet reprint preview"),
        )
        picture_scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        picture_scroller.set_child(self.preview_picture)
        self.preview_stack.add_named(picture_scroller, "picture")

        self.preview_status = Adw.StatusPage(
            icon_name="document-print-preview-symbolic",
            title=_("Preview unavailable"),
        )
        self.preview_stack.add_named(self.preview_status, "status")
        root.append(self.preview_stack)

        controls = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.previous_button = Gtk.Button(
            icon_name="go-previous-symbolic", tooltip_text=_("Previous selected page")
        )
        self.previous_button.connect("clicked", lambda _button: self._move_preview(-1))
        controls.append(self.previous_button)
        self.preview_page_label = Gtk.Label(label=_("Page 1"))
        controls.append(self.preview_page_label)
        self.next_button = Gtk.Button(
            icon_name="go-next-symbolic", tooltip_text=_("Next selected page")
        )
        self.next_button.connect("clicked", lambda _button: self._move_preview(1))
        controls.append(self.next_button)
        root.append(controls)
        return root

    def _select_original_printer(self) -> None:
        if self.prepared.job.printer in self.printers:
            self.printer_dropdown.set_selected(self.printers.index(self.prepared.job.printer))

    def _selected_printer(self) -> str | None:
        item = self.printer_dropdown.get_selected_item()
        return item.get_string() if item is not None else None

    def _printer_changed(self, *_args: object) -> None:
        if self._updating_controls:
            return
        self._load_destination_options()
        self._options_changed()

    def _load_destination_options(self) -> None:
        printer = self._selected_printer()
        capability = self.capabilities.get(printer or "")
        self._media_options = list(capability.media_options) if capability else []
        if self._media_options:
            labels = [
                f"{item.display_name} · {item.dimensions_text}"
                if item.dimensions_text
                else item.display_name
                for item in self._media_options
            ]
        else:
            labels = [_("Printer default (size unavailable)")]
        self._updating_controls = True
        try:
            self.media_dropdown.set_model(Gtk.StringList.new(labels))
            media_index = 0
            if capability and capability.default_media_keyword:
                for index, item in enumerate(self._media_options):
                    if item.keyword == capability.default_media_keyword:
                        media_index = index
                        break
            self.media_dropdown.set_selected(media_index)

            self._scaling_values = list(
                capability.scaling_supported if capability else ("fit", "fill", "none")
            )
            self.scaling_dropdown.set_model(
                Gtk.StringList.new([_scaling_label(value) for value in self._scaling_values])
            )
            scaling_index = 0
            if capability and capability.default_scaling in self._scaling_values:
                scaling_index = self._scaling_values.index(capability.default_scaling)
            self.scaling_dropdown.set_selected(scaling_index)
        finally:
            self._updating_controls = False
        self._update_media_tooltip()

    def _selected_media(self) -> MediaOption | None:
        index = int(self.media_dropdown.get_selected())
        return self._media_options[index] if index < len(self._media_options) else None

    def _update_media_tooltip(self) -> None:
        item = self.media_dropdown.get_selected_item()
        text = item.get_string() if item is not None else None
        self.media_dropdown.set_tooltip_text(text)

    def _selected_scaling(self) -> str:
        index = int(self.scaling_dropdown.get_selected())
        return self._scaling_values[index] if index < len(self._scaling_values) else "fit"

    def _exact_mode_changed(self, *_args: object) -> None:
        if self._updating_controls:
            return
        if self.exact_row.get_active():
            self._updating_controls = True
            try:
                self._select_original_printer()
                self.copies_row.set_value(1)
                self.all_pages_row.set_active(True)
            finally:
                self._updating_controls = False
            self._load_destination_options()
        self._update_mode()
        self._schedule_preview()

    def _update_mode(self) -> None:
        flexible = self._flexible_supported and not self.exact_row.get_active()
        self.printer_dropdown.set_sensitive(flexible)
        self.media_dropdown.set_sensitive(flexible)
        self.scaling_dropdown.set_sensitive(flexible)
        self.copies_row.set_sensitive(flexible)
        self.all_pages_row.set_sensitive(flexible and self.prepared.supports_page_selection)
        self.range_entry.set_sensitive(
            flexible
            and self.prepared.supports_page_selection
            and not self.all_pages_row.get_active()
        )
        if self.exact_row.get_active():
            self.preview_description.set_text(
                _("Original destination and retained CUPS options; the source page is shown unchanged.")
            )
        else:
            media = self._selected_media()
            media_text = (
                f"{media.display_name} ({media.dimensions_text})"
                if media and media.dimensions_text
                else (media.display_name if media else _("printer default paper"))
            )
            self.preview_description.set_text(
                _("{printer} · {paper} · {scaling}").format(
                    printer=self._selected_printer() or _("no printer"),
                    paper=media_text,
                    scaling=_scaling_label(self._selected_scaling()),
                )
            )

    def _pages_mode_changed(self, *_args: object) -> None:
        if self._updating_controls:
            return
        self._update_mode()
        if self.range_entry.get_sensitive():
            self.range_entry.grab_focus()
        self._preview_position = 0
        self._schedule_preview()

    def _range_changed(self, *_args: object) -> None:
        if self._updating_controls:
            return
        self._preview_position = 0
        self._schedule_preview()

    def _options_changed(self, *_args: object) -> None:
        if self._updating_controls:
            return
        self._update_media_tooltip()
        self._update_mode()
        self._schedule_preview()

    def _selection(self) -> PageSelection | None:
        if not self.prepared.total_pages:
            return None
        if self.all_pages_row.get_active():
            return all_pages(self.prepared.total_pages)
        return parse_page_range(self.range_entry.get_text(), self.prepared.total_pages)

    def _schedule_preview(self) -> None:
        self._preview_generation += 1
        if self._preview_timeout is not None:
            GLib.source_remove(self._preview_timeout)
        self._preview_timeout = GLib.timeout_add(180, self._start_preview)

    def _start_preview(self) -> bool:
        self._preview_timeout = None
        if not self.prepared.supports_page_selection:
            self.preview_status.set_title(_("Target-sheet preview unavailable"))
            self.preview_status.set_description(
                _("The retained job is not a readable PDF. Exact restart may still be available.")
            )
            self.preview_stack.set_visible_child_name("status")
            self.previous_button.set_sensitive(False)
            self.next_button.set_sensitive(False)
            return GLib.SOURCE_REMOVE
        try:
            selection = self._selection()
        except PageRangeError as error:
            self.preview_status.set_title(_("Enter a valid page range"))
            self.preview_status.set_description(str(error))
            self.preview_stack.set_visible_child_name("status")
            return GLib.SOURCE_REMOVE
        if selection is None or not selection.pages:
            return GLib.SOURCE_REMOVE
        self._preview_pages = selection.pages
        self._preview_position = min(self._preview_position, len(self._preview_pages) - 1)
        page_number = self._preview_pages[self._preview_position]
        self._update_preview_controls(page_number)
        exact = self.exact_row.get_active()
        media = None if exact else self._selected_media()
        scaling = "none" if exact else self._selected_scaling()
        generation = self._preview_generation
        self.preview_stack.set_visible_child_name("loading")
        self.runner.submit(
            lambda: self.service.create_reprint_preview(
                self.prepared,
                page_number=page_number,
                media=media,
                scaling=scaling,
            ),
            lambda path: self._preview_ready(path, generation, page_number),
            lambda error: self._preview_failed(error, generation),
        )
        return GLib.SOURCE_REMOVE

    def _update_preview_controls(self, page_number: int) -> None:
        self.preview_page_label.set_text(
            _("Page {page} · {position} of {count} selected").format(
                page=page_number,
                position=self._preview_position + 1,
                count=len(self._preview_pages),
            )
        )
        self.previous_button.set_sensitive(self._preview_position > 0)
        self.next_button.set_sensitive(self._preview_position + 1 < len(self._preview_pages))

    def _move_preview(self, delta: int) -> None:
        position = self._preview_position + delta
        if 0 <= position < len(self._preview_pages):
            self._preview_position = position
            self._schedule_preview()

    def _preview_ready(self, path: Path, generation: int, page_number: int) -> None:
        if generation != self._preview_generation:
            return
        if not self._preview_pages or self._preview_pages[self._preview_position] != page_number:
            return
        self.preview_picture.set_filename(str(path))
        self.preview_stack.set_visible_child_name("picture")

    def _preview_failed(self, error: BaseException, generation: int) -> None:
        if generation != self._preview_generation:
            return
        self.preview_status.set_title(_("Could not compose the preview"))
        self.preview_status.set_description(str(error))
        self.preview_stack.set_visible_child_name("status")

    def _print(self, _widget: Gtk.Widget) -> None:
        printer = self._selected_printer()
        if printer is None:
            show_message(self, _("No printer selected"), _("Choose a printer before continuing."))
            return
        try:
            selection = self._selection()
        except PageRangeError as error:
            show_message(self, _("Invalid page range"), str(error))
            return

        exact = self.exact_row.get_active()
        media = None if exact else self._selected_media()
        scaling = None if exact else self._selected_scaling()
        self.print_button.set_sensitive(False)
        self.print_button.set_label(_("Preparing…"))
        self.runner.submit(
            lambda: self.service.reprint(
                self.prepared,
                printer=printer,
                copies=int(self.copies_row.get_value()),
                selection=selection,
                preserve_original=exact,
                media_keyword=media.keyword if media else None,
                scaling=scaling,
            ),
            self._finished,
            self._failed,
        )

    def _finished(self, result: ReprintResult) -> None:
        self.close()
        self.on_complete(result)

    def _failed(self, error: BaseException) -> None:
        self.print_button.set_sensitive(True)
        self.print_button.set_label(_("Print"))
        show_message(self, _("Could not reprint this job"), str(error))
