from __future__ import annotations

from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

from .. import APP_NAME
from ..core.preview import render_pdf_page
from ..core.preview_view import (
    MAX_ZOOM_PERCENT,
    MIN_ZOOM_PERCENT,
    ZOOM_STEP_PERCENT,
    fit_zoom_percent,
    normalize_rotation,
    stepped_zoom,
    zoomed_dimensions,
)
from ..models import PreparedJob, PrintJob, ReprintResult
from ..util.async_runner import AsyncRunner
from ..util.i18n import _
from .about import show_about_dialog
from .authentication import CupsAuthenticationDialog
from .dialogs import confirm, show_message
from .printer_filter import PrinterFilterMenu
from .reprint_dialog import ReprintDialog
from .settings import SettingsWindow
from .widgets import labeled_button


FILTERS = ("All jobs", "Completed", "Active", "Canceled or aborted")


def _translation_markers() -> tuple[str, ...]:
    """Keep dynamic filter and IPP-state labels visible to xgettext."""
    return (
        _("All jobs"),
        _("Completed"),
        _("Active"),
        _("Canceled or aborted"),
        _("Waiting"),
        _("Held"),
        _("Printing"),
        _("Stopped"),
        _("Canceled"),
        _("Aborted"),
    )


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        application: Gtk.Application,
        service: object | None,
        runner: AsyncRunner,
        *,
        startup_error: str | None = None,
    ) -> None:
        super().__init__(application=application, title=APP_NAME)
        self.set_default_size(1120, 720)
        self.service = service
        self.runner = runner
        self.settings_window: SettingsWindow | None = None
        self.jobs: list[PrintJob] = []
        self._row_jobs: dict[Gtk.Widget, PrintJob] = {}
        self._prepared_cache: dict[int, PreparedJob] = {}
        self.current_job: PrintJob | None = None
        self.current_prepared: PreparedJob | None = None
        self.current_page = 1
        self._selection_generation = 0
        self._refresh_in_progress = False
        self._cups_restart_in_progress = False
        self._refresh_timer: int | None = None
        self._preview_source_pixbuf: GdkPixbuf.Pixbuf | None = None
        self._preview_rotated_pixbuf: GdkPixbuf.Pixbuf | None = None
        self._preview_rotation = 0
        self._preview_zoom_percent = 100.0
        self._preview_fit = True
        self._preview_zoom_updating = False
        self._preview_resize_source: int | None = None
        self._preview_viewport_size = (0, 0)
        self._preview_drag_start = (0.0, 0.0)
        self.authentication: CupsAuthenticationDialog | None = None
        if self.service is not None:
            self.authentication = CupsAuthenticationDialog(self)
            self.service.set_auth_provider(self.authentication.request_credentials)

        self.toast_overlay = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=APP_NAME))
        toolbar.add_top_bar(header)

        refresh = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text=_("Refresh (Ctrl+R)"),
        )
        refresh.set_action_name("app.refresh")
        header.pack_start(refresh)

        menu_model = Gio.Menu()
        menu_model.append(_("Settings"), "app.settings")
        menu_model.append(_("Welcome and initial setup"), "app.onboarding")
        menu_model.append(_("Check for updates"), "app.check-update")
        menu_model.append(_("About {app_name}").format(app_name=APP_NAME), "app.about")
        menu_model.append(_("Quit"), "app.quit")
        menu = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text=_("Main menu"),
            menu_model=menu_model,
        )
        header.pack_end(menu)

        toolbar.set_content(self._build_content())
        self.toast_overlay.set_child(toolbar)
        self.set_content(self.toast_overlay)

        if startup_error:
            self._show_startup_error(startup_error)
        else:
            self.refresh()
            self._refresh_timer = GLib.timeout_add_seconds(10, self._auto_refresh)
            self.connect("close-request", self._closing)

    def _build_content(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        filters = Gtk.Box(spacing=8)
        filters.set_margin_top(12)
        filters.set_margin_bottom(12)
        filters.set_margin_start(12)
        filters.set_margin_end(12)
        self.search = Gtk.SearchEntry(
            hexpand=True,
            placeholder_text=_("Search by name, user, printer, or job number"),
        )
        self.search.connect("search-changed", self._filters_changed)
        filters.append(self.search)

        self.printer_filter = PrinterFilterMenu(self._filters_changed)
        filters.append(self.printer_filter.button)

        self.filter_dropdown = Gtk.DropDown.new_from_strings([_(label) for label in FILTERS])
        self.filter_dropdown.set_tooltip_text(_("Filter by job state"))
        self.filter_dropdown.connect(
            "notify::selected", self._filters_changed
        )
        filters.append(self.filter_dropdown)
        root.append(filters)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True)
        paned.set_position(430)
        paned.set_resize_start_child(True)
        paned.set_shrink_start_child(False)
        paned.set_resize_end_child(True)
        paned.set_shrink_end_child(False)
        paned.set_start_child(self._build_job_browser())
        paned.set_end_child(self._build_details())
        root.append(paned)
        paned.set_vexpand(True)
        return root

    def _build_job_browser(self) -> Gtk.Widget:
        self.list_stack = Gtk.Stack()
        self.list_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        self.job_list = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            css_classes=["boxed-list"],
        )
        self.job_list.set_filter_func(self._filter_job_row)
        self.job_list.connect("row-selected", self._job_selected)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_margin_start(12)
        scroller.set_margin_end(6)
        scroller.set_margin_bottom(12)
        scroller.set_child(self.job_list)
        self.list_stack.add_named(scroller, "jobs")

        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        spinner.set_halign(Gtk.Align.CENTER)
        loading_box.append(spinner)
        loading_box.append(Gtk.Label(label=_("Loading print history…"), css_classes=["dim-label"]))
        self.list_stack.add_named(loading_box, "loading")

        self.empty_page = Adw.StatusPage(
            icon_name="printer-symbolic",
            title=_("No print jobs"),
            description=_("Jobs retained by the local CUPS service will appear here."),
        )
        self.list_stack.add_named(self.empty_page, "empty")
        return self.list_stack

    def _build_details(self) -> Gtk.Widget:
        self.detail_stack = Gtk.Stack()
        self.detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        welcome = Adw.StatusPage(
            icon_name="document-print-preview-symbolic",
            title=_("Select a print job"),
            description=_("Preview its retained file, export it, or reprint all or selected PDF pages."),
        )
        self.detail_stack.add_named(welcome, "welcome")

        self.detail_error = Adw.StatusPage(
            icon_name="dialog-error-symbolic",
            title=_("Print service unavailable"),
        )
        self.detail_stack.add_named(self.detail_error, "error")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        self.detail_title = Gtk.Label(
            xalign=0,
            ellipsize=3,
            selectable=True,
            css_classes=["title-2"],
        )
        content.append(self.detail_title)
        self.detail_meta = Gtk.Label(xalign=0, wrap=True, selectable=True, css_classes=["dim-label"])
        content.append(self.detail_meta)

        self.preview_stack = Gtk.Stack(vexpand=True, hexpand=True)
        self.preview_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        preview_loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        preview_loading.set_valign(Gtk.Align.CENTER)
        preview_spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        preview_spinner.set_halign(Gtk.Align.CENTER)
        preview_loading.append(preview_spinner)
        preview_loading.append(Gtk.Label(label=_("Retrieving the retained file…"), css_classes=["dim-label"]))
        self.preview_stack.add_named(preview_loading, "loading")

        self.preview_picture = Gtk.DrawingArea(
            content_width=1,
            content_height=1,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            tooltip_text=_(
                "Use the mouse wheel to zoom; drag to move an enlarged preview."
            ),
        )
        self.preview_picture.set_draw_func(self._draw_preview)
        self.preview_canvas = Gtk.Box(
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=True,
        )
        self.preview_canvas.set_margin_top(12)
        self.preview_canvas.set_margin_bottom(12)
        self.preview_canvas.set_margin_start(12)
        self.preview_canvas.set_margin_end(12)
        self.preview_canvas.append(self.preview_picture)
        self.preview_scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.preview_scroller.set_child(self.preview_canvas)

        scroll_zoom = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
            | Gtk.EventControllerScrollFlags.DISCRETE
        )
        scroll_zoom.connect("scroll", self._preview_scrolled)
        self.preview_scroller.add_controller(scroll_zoom)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._preview_drag_begin)
        drag.connect("drag-update", self._preview_drag_update)
        drag.connect("drag-end", self._preview_drag_end)
        self.preview_picture.add_controller(drag)

        preview_container = Gtk.Overlay(vexpand=True, hexpand=True)
        preview_container.set_child(self.preview_scroller)
        resize_observer = Gtk.DrawingArea(
            can_target=False,
            hexpand=True,
            vexpand=True,
        )
        resize_observer.connect("resize", self._preview_view_resized)
        preview_container.add_overlay(resize_observer)
        self.preview_stack.add_named(preview_container, "picture")

        self.text_buffer = Gtk.TextBuffer()
        text_view = Gtk.TextView(
            buffer=self.text_buffer,
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=12,
            right_margin=12,
            top_margin=12,
            bottom_margin=12,
        )
        text_scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        text_scroller.set_child(text_view)
        self.preview_stack.add_named(text_scroller, "text")

        self.preview_status = Adw.StatusPage(
            icon_name="document-print-symbolic",
            title=_("Preview unavailable"),
        )
        self.preview_stack.add_named(self.preview_status, "status")
        content.append(self.preview_stack)

        self.preview_controls = Gtk.Box(
            spacing=6,
            halign=Gtk.Align.CENTER,
            visible=False,
        )
        rotate_left = Gtk.Button(
            icon_name="object-rotate-left-symbolic",
            tooltip_text=_("Rotate preview left"),
        )
        rotate_left.connect("clicked", lambda _button: self._rotate_preview(-90))
        self.preview_controls.append(rotate_left)
        rotate_right = Gtk.Button(
            icon_name="object-rotate-right-symbolic",
            tooltip_text=_("Rotate preview right"),
        )
        rotate_right.connect("clicked", lambda _button: self._rotate_preview(90))
        self.preview_controls.append(rotate_right)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        separator.set_margin_top(6)
        separator.set_margin_bottom(6)
        self.preview_controls.append(separator)

        zoom_out = Gtk.Button(
            icon_name="zoom-out-symbolic",
            tooltip_text=_("Zoom out"),
        )
        zoom_out.connect("clicked", lambda _button: self._step_preview_zoom(-1))
        self.preview_controls.append(zoom_out)
        zoom_adjustment = Gtk.Adjustment(
            value=100,
            lower=MIN_ZOOM_PERCENT,
            upper=MAX_ZOOM_PERCENT,
            step_increment=ZOOM_STEP_PERCENT,
            page_increment=25,
        )
        self.preview_zoom = Gtk.SpinButton(
            adjustment=zoom_adjustment,
            digits=0,
            numeric=True,
            width_chars=4,
            tooltip_text=_("Zoom percentage"),
        )
        self.preview_zoom.set_update_policy(Gtk.SpinButtonUpdatePolicy.IF_VALID)
        self.preview_zoom.connect("value-changed", self._preview_zoom_changed)
        self.preview_controls.append(self.preview_zoom)
        self.preview_controls.append(Gtk.Label(label="%", css_classes=["dim-label"]))
        zoom_in = Gtk.Button(
            icon_name="zoom-in-symbolic",
            tooltip_text=_("Zoom in"),
        )
        zoom_in.connect("clicked", lambda _button: self._step_preview_zoom(1))
        self.preview_controls.append(zoom_in)
        fit = Gtk.Button(
            icon_name="zoom-fit-best-symbolic",
            tooltip_text=_("Fit preview to window"),
        )
        fit.connect("clicked", lambda _button: self._fit_preview())
        self.preview_controls.append(fit)
        actual_size = labeled_button(
            _("100%"),
            "zoom-original-symbolic",
            tooltip_text=_("Show preview at actual pixel size"),
        )
        actual_size.connect("clicked", lambda _button: self._set_actual_preview_size())
        self.preview_controls.append(actual_size)
        content.append(self.preview_controls)

        self.page_controls = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.previous_page = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text=_("Previous page"))
        self.previous_page.connect("clicked", lambda _button: self._show_pdf_page(self.current_page - 1))
        self.page_controls.append(self.previous_page)
        self.page_label = Gtk.Label(label=_("Page 1 of 1"))
        self.page_controls.append(self.page_label)
        self.next_page = Gtk.Button(icon_name="go-next-symbolic", tooltip_text=_("Next page"))
        self.next_page.connect("clicked", lambda _button: self._show_pdf_page(self.current_page + 1))
        self.page_controls.append(self.next_page)
        self.page_controls.set_visible(False)
        content.append(self.page_controls)

        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.delete_button = Gtk.Button(
            icon_name="user-trash-symbolic",
            tooltip_text=_("Permanently delete this retained job"),
            css_classes=["destructive-action"],
        )
        self.delete_button.connect("clicked", self._confirm_delete)
        actions.append(self.delete_button)
        self.export_button = labeled_button(
            _("Export original"),
            "document-save-symbolic",
            sensitive=False,
        )
        self.export_button.connect("clicked", self._export)
        actions.append(self.export_button)
        self.reprint_button = labeled_button(
            _("Reprint"),
            "document-print-symbolic",
            sensitive=False,
            css_classes=["suggested-action"],
        )
        self.reprint_button.connect("clicked", self._open_reprint)
        actions.append(self.reprint_button)
        content.append(actions)

        self.detail_stack.add_named(content, "details")
        self.detail_stack.set_visible_child_name("welcome")
        return self.detail_stack

    def refresh(self) -> None:
        if (
            self.service is None
            or self._refresh_in_progress
            or self._cups_restart_in_progress
        ):
            return
        self._refresh_in_progress = True
        if not self.jobs:
            self.list_stack.set_visible_child_name("loading")
        self.runner.submit(self.service.list_jobs, self._jobs_loaded, self._jobs_failed)

    def _jobs_loaded(self, jobs: list[PrintJob]) -> None:
        self._refresh_in_progress = False
        if self._cups_restart_in_progress:
            return
        selected_job_id = self.current_job.job_id if self.current_job else None
        self.jobs = jobs
        # Update the checklist before rows are added. Gtk.ListBox evaluates its
        # filter as each row enters the model; on the first load the printer
        # selection is still empty until this call populates "All printers".
        self.printer_filter.update_printers([job.printer for job in jobs])
        self._row_jobs.clear()
        while child := self.job_list.get_first_child():
            self.job_list.remove(child)
        for job in jobs:
            row = self._job_row(job)
            self._row_jobs[row] = job
            self.job_list.append(row)
        # Re-evaluate explicitly as a guard for GTK versions that cache the
        # visibility decided while rebuilding the list.
        self.job_list.invalidate_filter()
        self.list_stack.set_visible_child_name("jobs" if jobs else "empty")
        if jobs:
            if selected_job_id is None or not self._select_job(selected_job_id):
                self._select_first_visible_job()

    def _jobs_failed(self, error: BaseException) -> None:
        self._refresh_in_progress = False
        if self._cups_restart_in_progress:
            return
        self.empty_page.set_title(_("Could not load print history"))
        self.empty_page.set_description(str(error))
        self.empty_page.set_icon_name("dialog-error-symbolic")
        self.list_stack.set_visible_child_name("empty")
        self.detail_error.set_description(str(error))
        self.detail_stack.set_visible_child_name("error")

    def _show_startup_error(self, error: str) -> None:
        self.empty_page.set_title(_("Print service unavailable"))
        self.empty_page.set_description(error)
        self.empty_page.set_icon_name("dialog-error-symbolic")
        self.list_stack.set_visible_child_name("empty")
        self.detail_error.set_description(error)
        self.detail_stack.set_visible_child_name("error")

    def _job_row(self, job: PrintJob) -> Adw.ActionRow:
        date = _format_date(job.date)
        pages = (
            _("{count} pages").format(count=job.pages)
            if job.pages is not None
            else _("page count unknown")
        )
        row = Adw.ActionRow(
            title=job.title,
            subtitle=f"#{job.job_id} · {date}\n{job.printer} · {job.user} · {pages}",
            icon_name="document-print-symbolic",
        )
        status = Gtk.Label(label=_(job.state_label), valign=Gtk.Align.CENTER, css_classes=["caption"])
        row.add_suffix(status)
        return row

    def _filter_job_row(self, row: Gtk.ListBoxRow) -> bool:
        job = self._row_jobs.get(row)
        if job is None:
            return True
        query = self.search.get_text().strip().casefold()
        haystack = " ".join(
            (str(job.job_id), job.title, job.user, job.printer, job.state_label)
        ).casefold()
        if query and query not in haystack:
            return False
        if not self.printer_filter.matches(job.printer):
            return False
        selected_filter = self.filter_dropdown.get_selected()
        if selected_filter == 1:
            return job.state == 9
        if selected_filter == 2:
            return job.state in {3, 4, 5, 6}
        if selected_filter == 3:
            return job.state in {7, 8}
        return True

    def _filters_changed(self, *_args: object) -> None:
        self.job_list.invalidate_filter()
        selected = self.job_list.get_selected_row()
        if selected is None or not self._filter_job_row(selected):
            self._select_first_visible_job()

    def _select_first_visible_job(self) -> None:
        row = self.job_list.get_first_child()
        while row is not None:
            if self._filter_job_row(row):
                self.job_list.select_row(row)
                return
            row = row.get_next_sibling()
        self.job_list.unselect_all()

    def _select_job(self, job_id: int) -> bool:
        row = self.job_list.get_first_child()
        while row is not None:
            job = self._row_jobs.get(row)
            if job and job.job_id == job_id and self._filter_job_row(row):
                self.job_list.select_row(row)
                return True
            row = row.get_next_sibling()
        return False

    def _auto_refresh(self) -> bool:
        if self.get_mapped():
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def _closing(self, _window: Gtk.Window) -> bool:
        if self._refresh_timer is not None:
            GLib.source_remove(self._refresh_timer)
            self._refresh_timer = None
        return False

    def _job_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        job = self._row_jobs.get(row)
        if job is None:
            return
        if (
            self.current_job is not None
            and self.current_job.job_id == job.job_id
            and self.current_job.state == job.state
            and self.current_job.preserved == job.preserved
            and self.current_prepared is not None
            and self.current_prepared.preview_kind != "unavailable"
        ):
            self.current_job = job
            return
        self._selection_generation += 1
        generation = self._selection_generation
        self.current_job = job
        self.current_prepared = None
        self.current_page = 1
        self._reset_preview_view()
        self.detail_title.set_text(job.title)
        preserved = _("yes") if job.preserved is True else _("no") if job.preserved is False else _("unknown")
        size = f"{job.size_kib} KiB" if job.size_kib is not None else _("unknown size")
        self.detail_meta.set_text(
            _("Job #{job_id} · {state} · {printer} · {user}\n"
              "Created {created} · CUPS retention flag: {preserved} · {size}").format(
                job_id=job.job_id,
                state=_(job.state_label),
                printer=job.printer,
                user=job.user,
                created=_format_date(job.created_at),
                preserved=preserved,
                size=size,
            )
        )
        self.detail_stack.set_visible_child_name("details")
        self.preview_stack.set_visible_child_name("loading")
        self.page_controls.set_visible(False)
        self.reprint_button.set_sensitive(False)
        self.export_button.set_sensitive(False)
        self.delete_button.set_sensitive(True)

        cached = self._prepared_cache.get(job.job_id)
        if cached is not None:
            self._prepared(job, cached, generation)
            return
        self.runner.submit(
            lambda: self.service.retrieve_job(job),
            lambda prepared: self._prepared(job, prepared, generation),
            lambda error: self._prepare_failed(job, error, generation),
        )

    def _prepared(self, job: PrintJob, prepared: PreparedJob, generation: int) -> None:
        self._prepared_cache[job.job_id] = prepared
        if generation != self._selection_generation or self.current_job != job:
            return
        self.current_prepared = prepared
        self.reprint_button.set_sensitive(job.can_restart)
        self.export_button.set_sensitive(prepared.printable_path is not None)
        self._display_prepared(prepared)

    def _prepare_failed(self, job: PrintJob, error: BaseException, generation: int) -> None:
        unavailable = PreparedJob(job, (), None, None, "unavailable")
        if generation != self._selection_generation or self.current_job != job:
            return
        self.current_prepared = unavailable
        self.reprint_button.set_sensitive(job.can_restart)
        self.preview_status.set_title(_("Could not access the retained file"))
        self.preview_status.set_description(str(error))
        self.preview_status.set_icon_name("dialog-warning-symbolic")
        self.preview_stack.set_visible_child_name("status")

    def _display_prepared(self, prepared: PreparedJob) -> None:
        self.page_controls.set_visible(False)
        if prepared.preview_kind == "pdf" and prepared.printable_path and prepared.total_pages:
            self.page_controls.set_visible(True)
            self._show_pdf_page(1)
        elif prepared.preview_kind == "image" and prepared.printable_path:
            self._show_visual_preview(prepared.printable_path)
        elif prepared.preview_kind == "text" and prepared.printable_path:
            self.preview_controls.set_visible(False)
            data = prepared.printable_path.read_bytes()[:262_144]
            text = data.decode("utf-8", errors="replace")
            if prepared.printable_path.stat().st_size > len(data):
                text += "\n\n[Preview truncated at 256 KiB]"
            self.text_buffer.set_text(text)
            self.preview_stack.set_visible_child_name("text")
        else:
            self.preview_controls.set_visible(False)
            descriptions = {
                "raw": _("The retained format can be reprinted, but this version cannot render it safely."),
                "mixed": _("This multi-document job contains mixed formats and has no combined preview."),
                "unavailable": _("CUPS no longer has the spool file. Metadata remains visible."),
            }
            self.preview_status.set_title(_("Preview unavailable"))
            self.preview_status.set_description(
                descriptions.get(prepared.preview_kind, _("No preview is available for this job."))
            )
            self.preview_status.set_icon_name("document-print-symbolic")
            self.preview_stack.set_visible_child_name("status")

    def _show_pdf_page(self, page: int) -> None:
        prepared = self.current_prepared
        if not prepared or not prepared.printable_path or not prepared.total_pages:
            return
        page = max(1, min(page, prepared.total_pages))
        self.current_page = page
        self.page_label.set_text(
            _("Page {page} of {total}").format(page=page, total=prepared.total_pages)
        )
        self.previous_page.set_sensitive(page > 1)
        self.next_page.set_sensitive(page < prepared.total_pages)
        self.preview_stack.set_visible_child_name("loading")
        generation = self._selection_generation
        job_id = prepared.job.job_id
        self.runner.submit(
            lambda: render_pdf_page(prepared.printable_path, page, self.service.store),
            lambda path: self._pdf_rendered(path, page, job_id, generation),
            lambda error: self._pdf_render_failed(error, job_id, generation),
        )

    def _pdf_rendered(self, path: Path, page: int, job_id: int, generation: int) -> None:
        if (
            generation != self._selection_generation
            or self.current_job is None
            or self.current_job.job_id != job_id
            or self.current_page != page
        ):
            return
        self._show_visual_preview(path)

    def _pdf_render_failed(self, error: BaseException, job_id: int, generation: int) -> None:
        if (
            generation != self._selection_generation
            or self.current_job is None
            or self.current_job.job_id != job_id
        ):
            return
        self.preview_status.set_title(_("Could not render this PDF"))
        self.preview_status.set_description(str(error))
        self.preview_status.set_icon_name("dialog-warning-symbolic")
        self.preview_controls.set_visible(False)
        self.preview_stack.set_visible_child_name("status")

    def _reset_preview_view(self) -> None:
        self._preview_source_pixbuf = None
        self._preview_rotated_pixbuf = None
        self._preview_rotation = 0
        self._preview_zoom_percent = 100.0
        self._preview_fit = True
        self.preview_picture.set_content_width(1)
        self.preview_picture.set_content_height(1)
        self.preview_picture.queue_draw()
        self.preview_controls.set_visible(False)
        self._update_zoom_control(100.0)

    def _show_visual_preview(self, path: Path) -> None:
        try:
            source = GdkPixbuf.Pixbuf.new_from_file(str(path))
        except Exception as error:
            self.preview_status.set_title(_("Could not render this preview"))
            self.preview_status.set_description(str(error))
            self.preview_status.set_icon_name("dialog-warning-symbolic")
            self.preview_controls.set_visible(False)
            self.preview_stack.set_visible_child_name("status")
            return
        self._preview_source_pixbuf = source
        self._preview_rotated_pixbuf = None
        self._apply_preview_transform()
        self.preview_controls.set_visible(True)
        self.preview_stack.set_visible_child_name("picture")

    def _rotated_preview(self) -> GdkPixbuf.Pixbuf | None:
        source = self._preview_source_pixbuf
        if source is None:
            return None
        if self._preview_rotated_pixbuf is not None:
            return self._preview_rotated_pixbuf
        rotations = {
            90: GdkPixbuf.PixbufRotation.CLOCKWISE,
            180: GdkPixbuf.PixbufRotation.UPSIDEDOWN,
            270: GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE,
        }
        rotation = rotations.get(self._preview_rotation)
        rotated = source if rotation is None else source.rotate_simple(rotation)
        self._preview_rotated_pixbuf = rotated or source
        return self._preview_rotated_pixbuf

    def _apply_preview_transform(self) -> bool:
        pixbuf = self._rotated_preview()
        if pixbuf is None:
            return GLib.SOURCE_REMOVE
        center = self._preview_scroll_center()
        if self._preview_fit:
            self._preview_zoom_percent = fit_zoom_percent(
                pixbuf.get_width(),
                pixbuf.get_height(),
                self._preview_viewport_size[0],
                self._preview_viewport_size[1],
            )
        width, height = zoomed_dimensions(
            pixbuf.get_width(),
            pixbuf.get_height(),
            self._preview_zoom_percent,
        )
        self.preview_picture.set_content_width(width)
        self.preview_picture.set_content_height(height)
        self.preview_picture.queue_draw()
        self._update_zoom_control(self._preview_zoom_percent)
        GLib.idle_add(self._restore_preview_scroll_center, center)
        return GLib.SOURCE_REMOVE

    def _draw_preview(
        self,
        _area: Gtk.DrawingArea,
        context: object,
        width: int,
        height: int,
    ) -> None:
        pixbuf = self._rotated_preview()
        if pixbuf is None or width <= 0 or height <= 0:
            return
        context.save()
        context.scale(
            width / pixbuf.get_width(),
            height / pixbuf.get_height(),
        )
        Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
        context.paint()
        context.restore()

    def _update_zoom_control(self, percent: float) -> None:
        self._preview_zoom_updating = True
        self.preview_zoom.set_value(round(percent))
        self._preview_zoom_updating = False

    def _preview_zoom_changed(self, _spin: Gtk.SpinButton) -> None:
        if self._preview_zoom_updating or self._preview_source_pixbuf is None:
            return
        self._preview_fit = False
        self._preview_zoom_percent = self.preview_zoom.get_value()
        self._apply_preview_transform()

    def _step_preview_zoom(self, steps: int) -> None:
        if self._preview_source_pixbuf is None:
            return
        self._preview_fit = False
        self._preview_zoom_percent = stepped_zoom(self._preview_zoom_percent, steps)
        self._apply_preview_transform()

    def _preview_scrolled(
        self,
        _controller: Gtk.EventControllerScroll,
        _delta_x: float,
        delta_y: float,
    ) -> bool:
        if self._preview_source_pixbuf is None or delta_y == 0:
            return False
        self._step_preview_zoom(1 if delta_y < 0 else -1)
        return True

    def _fit_preview(self) -> None:
        if self._preview_source_pixbuf is None:
            return
        self._preview_fit = True
        self._apply_preview_transform()

    def _set_actual_preview_size(self) -> None:
        if self._preview_source_pixbuf is None:
            return
        self._preview_fit = False
        self._preview_zoom_percent = 100.0
        self._apply_preview_transform()

    def _rotate_preview(self, degrees: int) -> None:
        if self._preview_source_pixbuf is None:
            return
        self._preview_rotation = normalize_rotation(self._preview_rotation + degrees)
        self._preview_rotated_pixbuf = None
        self._apply_preview_transform()

    def _preview_view_resized(
        self,
        _observer: Gtk.DrawingArea,
        width: int,
        height: int,
    ) -> None:
        self._preview_viewport_size = (width, height)
        if (
            not self._preview_fit
            or self._preview_source_pixbuf is None
            or self._preview_resize_source is not None
        ):
            return
        self._preview_resize_source = GLib.idle_add(self._fit_preview_after_resize)

    def _fit_preview_after_resize(self) -> bool:
        self._preview_resize_source = None
        if self._preview_fit:
            self._apply_preview_transform()
        return GLib.SOURCE_REMOVE

    def _preview_scroll_center(self) -> tuple[float, float]:
        horizontal = self.preview_scroller.get_hadjustment()
        vertical = self.preview_scroller.get_vadjustment()
        return (
            (horizontal.get_value() + horizontal.get_page_size() / 2)
            / max(1.0, horizontal.get_upper()),
            (vertical.get_value() + vertical.get_page_size() / 2)
            / max(1.0, vertical.get_upper()),
        )

    def _restore_preview_scroll_center(self, center: tuple[float, float]) -> bool:
        for adjustment, position in zip(
            (
                self.preview_scroller.get_hadjustment(),
                self.preview_scroller.get_vadjustment(),
            ),
            center,
        ):
            value = position * adjustment.get_upper() - adjustment.get_page_size() / 2
            maximum = max(adjustment.get_lower(), adjustment.get_upper() - adjustment.get_page_size())
            adjustment.set_value(max(adjustment.get_lower(), min(maximum, value)))
        return GLib.SOURCE_REMOVE

    def _preview_drag_begin(
        self,
        _gesture: Gtk.GestureDrag,
        _start_x: float,
        _start_y: float,
    ) -> None:
        self._preview_drag_start = (
            self.preview_scroller.get_hadjustment().get_value(),
            self.preview_scroller.get_vadjustment().get_value(),
        )
        self.preview_picture.set_cursor_from_name("grabbing")

    def _preview_drag_update(
        self,
        _gesture: Gtk.GestureDrag,
        offset_x: float,
        offset_y: float,
    ) -> None:
        horizontal = self.preview_scroller.get_hadjustment()
        vertical = self.preview_scroller.get_vadjustment()
        horizontal.set_value(self._preview_drag_start[0] - offset_x)
        vertical.set_value(self._preview_drag_start[1] - offset_y)

    def _preview_drag_end(
        self,
        _gesture: Gtk.GestureDrag,
        _offset_x: float,
        _offset_y: float,
    ) -> None:
        self.preview_picture.set_cursor_from_name("grab")

    def _open_reprint(self, _button: Gtk.Button) -> None:
        if self.current_prepared is None:
            return
        self.reprint_button.set_sensitive(False)
        self.runner.submit(
            self.service.list_reprint_destinations,
            self._printers_loaded,
            self._printers_failed,
        )

    def _printers_loaded(self, result: tuple[list[str], dict[str, object]]) -> None:
        self.reprint_button.set_sensitive(True)
        prepared = self.current_prepared
        if prepared is None:
            return
        printers, capabilities = result
        if prepared.job.printer not in printers:
            printers.insert(0, prepared.job.printer)
        dialog = ReprintDialog(
            prepared,
            printers,
            capabilities,
            self.service,
            self.runner,
            self._reprint_complete,
        )
        dialog.present(self)

    def _printers_failed(self, error: BaseException) -> None:
        self.reprint_button.set_sensitive(True)
        show_message(self, _("Could not list printers"), str(error))

    def _reprint_complete(self, result: ReprintResult) -> None:
        if result.restarted_original:
            message = _("Job #{job_id} was restarted with all pages.").format(job_id=result.job_id)
        else:
            message = _("New job #{job_id} was created for pages {pages}.").format(
                job_id=result.job_id, pages=result.page_description
            )
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=6))
        self.refresh()

    def _export(self, _button: Gtk.Button) -> None:
        prepared = self.current_prepared
        if not prepared or not prepared.printable_path:
            return
        source = prepared.printable_path
        name = _safe_export_name(prepared.job.title, source.suffix)
        dialog = Gtk.FileDialog(title=_("Export retained document"), initial_name=name)

        def chosen(source_dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                file = source_dialog.save_finish(result)
            except Exception:
                return
            destination = Path(file.get_path())
            self.runner.submit(
                lambda: self.service.export_original(prepared, destination),
                lambda path: self.toast_overlay.add_toast(
                    Adw.Toast(title=_("Exported to {name}").format(name=path.name), timeout=5)
                ),
                lambda error: show_message(self, _("Could not export this job"), str(error)),
            )

        dialog.save(self, None, chosen)

    def _confirm_delete(self, _button: Gtk.Button) -> None:
        job = self.current_job
        if job is None:
            return
        confirm(
            self,
            _("Delete job #{job_id}?").format(job_id=job.job_id),
            _("The retained file and its history metadata will be permanently purged from CUPS."),
            _("Delete"),
            lambda: self._delete_job(job),
        )

    def _delete_job(self, job: PrintJob) -> None:
        self.delete_button.set_sensitive(False)
        self.runner.submit(
            lambda: self.service.purge_job(job.job_id),
            lambda _result: self._deleted(job),
            lambda error: self._delete_failed(error),
        )

    def _deleted(self, job: PrintJob) -> None:
        self._prepared_cache.pop(job.job_id, None)
        self.toast_overlay.add_toast(
            Adw.Toast(title=_("Job #{job_id} deleted").format(job_id=job.job_id), timeout=5)
        )
        self.detail_stack.set_visible_child_name("welcome")
        self.refresh()

    def _delete_failed(self, error: BaseException) -> None:
        self.delete_button.set_sensitive(True)
        show_message(self, _("Could not delete this job"), str(error))

    def show_settings(self) -> None:
        if self.service is None:
            return
        if self.settings_window is None:
            application = self.get_application()
            wait_for_cups_restart = getattr(
                application,
                "wait_for_cups_restart",
            )
            self.settings_window = SettingsWindow(
                application,
                self.service,
                self.runner,
                self.refresh,
                wait_for_cups_restart,
            )
            self.settings_window.connect("close-request", self._settings_closed)
        self.settings_window.present()

    def set_cups_restart_in_progress(self, active: bool) -> None:
        self._cups_restart_in_progress = active
        if not active:
            self.refresh()

    def _settings_closed(self, _window: Gtk.Window) -> bool:
        self.settings_window = None
        return False

    def show_about(self) -> None:
        application = self.get_application()
        check_for_updates = getattr(application, "check_for_updates", None)
        show_about_dialog(self, check_for_updates, self.service)


def _format_date(value: datetime | None) -> str:
    if value is None:
        return _("unknown date")
    return value.strftime("%Y-%m-%d %H:%M")


def _safe_export_name(title: str, suffix: str) -> str:
    safe = "".join(character if character.isalnum() or character in " ._-" else "_" for character in title)
    safe = safe.strip(" .") or "print-job"
    if not suffix:
        suffix = ".bin"
    if not safe.lower().endswith(suffix.lower()):
        safe += suffix
    return safe
