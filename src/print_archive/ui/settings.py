from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from .. import APP_NAME
from ..models import CupsServerSettings, CupsSystemInfo, RetentionSettings
from ..util.async_runner import AsyncRunner
from ..util.i18n import _
from .dialogs import confirm, show_message


def _spin_row(title: str, lower: int, upper: int, value: int) -> Adw.SpinRow:
    adjustment = Gtk.Adjustment(
        value=value,
        lower=lower,
        upper=upper,
        step_increment=1,
        page_increment=10,
    )
    return Adw.SpinRow(title=title, adjustment=adjustment)


class SettingsWindow(Adw.ApplicationWindow):
    """Global CUPS preferences; intentionally contains no printer editor."""

    def __init__(
        self,
        application: Gtk.Application,
        service: object,
        runner: AsyncRunner,
        on_history_changed: Callable[[], object],
        wait_for_cups_restart: Callable[
            [Gtk.Window, Callable[[], object]],
            None,
        ],
    ) -> None:
        super().__init__(
            application=application,
            title=_("{app_name} Settings").format(app_name=APP_NAME),
        )
        self.set_default_size(760, 720)
        self.service = service
        self.runner = runner
        self.on_history_changed = on_history_changed
        self.wait_for_cups_restart = wait_for_cups_restart
        self._retention_editor_enabled = False
        self._server_editor_enabled = False

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        self.page_stack = Adw.ViewStack(vexpand=True)
        self.page_stack.add_titled_with_icon(
            self._scroll_page(self._build_retention_page()),
            "retention",
            _("Retention"),
            "document-save-symbolic",
        )
        self.page_stack.add_titled_with_icon(
            self._scroll_page(self._build_server_page()),
            "server",
            _("Server"),
            "network-server-symbolic",
        )
        self.page_stack.add_titled_with_icon(
            self._scroll_page(self._build_maintenance_page()),
            "maintenance",
            _("Maintenance"),
            "applications-system-symbolic",
        )
        switcher = Adw.ViewSwitcher()
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_stack(self.page_stack)
        header.set_title_widget(switcher)
        toolbar.set_content(self.page_stack)

        self.footer_stack = Gtk.Stack()
        self.footer_stack.add_named(self._build_retention_footer(), "retention")
        self.footer_stack.add_named(self._build_server_footer(), "server")
        toolbar.add_bottom_bar(self.footer_stack)
        self.page_stack.connect("notify::visible-child-name", self._visible_page_changed)
        self._visible_page_changed()

        self.set_content(toolbar)
        self._set_retention_sensitive(False)
        self._set_server_sensitive(False)
        self._reload_all()

    @staticmethod
    def _scroll_page(page: Adw.PreferencesPage) -> Gtk.ScrolledWindow:
        scroller = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        scroller.set_child(page)
        return scroller

    def _build_apply_footer(
        self,
        callback: Callable[[Gtk.Button], None],
    ) -> tuple[Gtk.Box, Gtk.Label, Gtk.Button]:
        footer = Gtk.Box(spacing=12)
        footer.set_margin_top(9)
        footer.set_margin_bottom(9)
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        status = Gtk.Label(
            label=_("Loading current CUPS values…"),
            xalign=0,
            wrap=True,
            hexpand=True,
            css_classes=["dim-label"],
        )
        footer.append(status)
        button = Gtk.Button(
            label=_("Apply"),
            valign=Gtk.Align.CENTER,
            css_classes=["suggested-action"],
        )
        button.connect("clicked", callback)
        footer.append(button)
        return footer, status, button

    def _build_retention_footer(self) -> Gtk.Widget:
        footer, self.retention_footer_status, self.retention_apply_button = (
            self._build_apply_footer(self._apply_retention)
        )
        return footer

    def _build_server_footer(self) -> Gtk.Widget:
        footer, self.server_footer_status, self.server_apply_button = (
            self._build_apply_footer(self._apply_server)
        )
        return footer

    def _visible_page_changed(self, *_args: object) -> None:
        name = self.page_stack.get_visible_child_name()
        self.footer_stack.set_visible(name in {"retention", "server"})
        if name in {"retention", "server"}:
            self.footer_stack.set_visible_child_name(name)

    @staticmethod
    def _set_footer_status(label: Gtk.Label, text: str, detail: str | None = None) -> None:
        label.set_text(text)
        label.set_tooltip_text(detail)

    def _build_retention_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title=_("Retention"), icon_name="document-save-symbolic")

        behavior = Adw.PreferencesGroup()
        behavior.add(
            Adw.ActionRow(
                title=_("No automatic configuration changes"),
                subtitle=_(
                    "Installing or opening {app_name} does not change CUPS. "
                    "Live values are loaded here and only Apply saves edits."
                ).format(app_name=APP_NAME),
                icon_name="dialog-information-symbolic",
            )
        )
        page.add(behavior)

        files = Adw.PreferencesGroup(
            title=_("Retained print files"),
            description=_(
                "CUPS needs the spool file for preview, export, and reprinting. "
                "Its standard default is 1 day (86,400 seconds). No time limit "
                "still depends on MaxJobs and can use substantial disk space."
            ),
        )
        self.files_unlimited = Adw.SwitchRow(
            title=_("No time limit for retained files"),
            subtitle="PreserveJobFiles=Yes",
            active=False,
        )
        self.files_unlimited.connect("notify::active", self._files_mode_changed)
        files.add(self.files_unlimited)
        self.files_days = _spin_row(_("Otherwise keep files for (days)"), 1, 3650, 1)
        files.add(self.files_days)
        page.add(files)

        history = Adw.PreferencesGroup(
            title=_("Job history"),
            description=_(
                "History is metadata such as job name, user, printer, and status. "
                "CUPS normally keeps it without a time limit, capped by MaxJobs 500."
            ),
        )
        self.history_unlimited = Adw.SwitchRow(
            title=_("No time limit for history"),
            subtitle="PreserveJobHistory=Yes",
            active=True,
        )
        self.history_unlimited.connect("notify::active", self._history_mode_changed)
        history.add(self.history_unlimited)
        self.history_days = _spin_row(_("Otherwise keep history for (days)"), 1, 3650, 1)
        history.add(self.history_days)
        page.add(history)

        capacity = Adw.PreferencesGroup(
            title=_("Capacity"),
            description=_(
                "MaxJobs limits the number of retained jobs. Zero means unlimited; "
                "disk usage then depends on the file and history limits."
            ),
        )
        self.max_jobs_unlimited = Adw.SwitchRow(
            title=_("Unlimited number of jobs"),
            subtitle="MaxJobs=0",
            active=False,
        )
        self.max_jobs_unlimited.connect("notify::active", self._max_jobs_mode_changed)
        capacity.add(self.max_jobs_unlimited)
        self.max_jobs = _spin_row(_("Otherwise keep at most"), 1, 1_000_000, 500)
        capacity.add(self.max_jobs)
        page.add(capacity)

        actions = Adw.PreferencesGroup(title=_("Defaults"))
        self.defaults_row = Adw.ActionRow(
            title=_("Load CUPS standard defaults into the form"),
            subtitle=_("Files: 1 day · History: no time limit · MaxJobs: 500"),
            icon_name="edit-undo-symbolic",
            activatable=True,
        )
        self.defaults_row.connect("activated", self._set_defaults)
        actions.add(self.defaults_row)
        page.add(actions)
        return page

    def _build_server_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title=_("Server"), icon_name="network-server-symbolic")
        scope = Adw.PreferencesGroup()
        scope.add(
            Adw.ActionRow(
                title=_("Global CUPS settings only"),
                subtitle=_(
                    "These switches apply to the print server as a whole. "
                    "Printers, drivers, queues, defaults, and per-printer options are not managed here."
                ),
                icon_name="dialog-information-symbolic",
            )
        )
        page.add(scope)

        access = Adw.PreferencesGroup(
            title=_("Access and sharing"),
            description=_("Changing network access can expose print administration or queues to other devices."),
        )
        self.web_interface = Adw.SwitchRow(
            title=_("Enable CUPS web interface"),
            subtitle="WebInterface",
        )
        access.add(self.web_interface)
        self.share_printers = Adw.SwitchRow(
            title=_("Share local printers"),
            subtitle="cupsctl --share-printers",
        )
        access.add(self.share_printers)
        self.remote_admin = Adw.SwitchRow(
            title=_("Allow remote administration"),
            subtitle="cupsctl --remote-admin",
        )
        access.add(self.remote_admin)
        self.remote_any = Adw.SwitchRow(
            title=_("Allow connections from any network"),
            subtitle=_("High-risk option: removes the local-subnet access restriction."),
        )
        access.add(self.remote_any)
        self.user_cancel_any = Adw.SwitchRow(
            title=_("Allow users to cancel any job"),
            subtitle="cupsctl --user-cancel-any",
        )
        access.add(self.user_cancel_any)
        page.add(access)

        diagnostics = Adw.PreferencesGroup(title=_("Diagnostics"))
        self.debug_logging = Adw.SwitchRow(
            title=_("Enable debug logging"),
            subtitle=_("Produces more CUPS log data and should normally remain off."),
        )
        diagnostics.add(self.debug_logging)
        page.add(diagnostics)

        return page

    def _build_maintenance_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title=_("Maintenance"), icon_name="applications-system-symbolic")
        info = Adw.PreferencesGroup(title=_("Local print service"))
        self.system_info_row = Adw.ActionRow(
            title=_("Reading CUPS information…"),
            subtitle=_("Server, user, version, default destination, and queue count."),
            icon_name="printer-symbolic",
        )
        info.add(self.system_info_row)
        page.add(info)

        tools = Adw.PreferencesGroup(title=_("Tools"))
        web = Adw.ActionRow(
            title=_("Open CUPS web interface"),
            subtitle="http://localhost:631",
            icon_name="web-browser-symbolic",
            activatable=True,
        )
        web.connect("activated", self._open_cups_web)
        tools.add(web)
        refresh = Adw.ActionRow(
            title=_("Refresh all live values"),
            subtitle=_("Reload retention, global server settings, and service information."),
            icon_name="view-refresh-symbolic",
            activatable=True,
        )
        refresh.connect("activated", lambda _row: self._reload_all())
        tools.add(refresh)
        page.add(tools)

        destructive = Adw.PreferencesGroup(title=_("History data"))
        clear = Adw.ActionRow(
            title=_("Delete all job history now"),
            subtitle=_("Purges retained files and metadata for every job visible to CUPS."),
            icon_name="user-trash-symbolic",
            activatable=True,
        )
        clear.add_css_class("error")
        clear.connect("activated", self._confirm_clear)
        destructive.add(clear)
        page.add(destructive)
        return page

    def _reload_all(self) -> None:
        self._set_retention_sensitive(False)
        self._set_server_sensitive(False)
        self._set_footer_status(
            self.retention_footer_status,
            _("Loading current CUPS values…"),
        )
        self._set_footer_status(
            self.server_footer_status,
            _("Loading current CUPS values…"),
        )
        self.system_info_row.set_title(_("Reading CUPS information…"))
        self.runner.submit(
            self.service.read_retention_settings,
            self._retention_loaded,
            self._retention_failed,
        )
        self.runner.submit(
            self.service.read_server_settings,
            self._server_loaded,
            self._server_failed,
        )
        self.runner.submit(
            self.service.read_system_info,
            self._system_info_loaded,
            self._system_info_failed,
        )

    def _files_mode_changed(self, *_args: object) -> None:
        self.files_days.set_sensitive(
            self._retention_editor_enabled and not self.files_unlimited.get_active()
        )

    def _history_mode_changed(self, *_args: object) -> None:
        self.history_days.set_sensitive(
            self._retention_editor_enabled and not self.history_unlimited.get_active()
        )

    def _max_jobs_mode_changed(self, *_args: object) -> None:
        self.max_jobs.set_sensitive(
            self._retention_editor_enabled and not self.max_jobs_unlimited.get_active()
        )

    def _set_defaults(self, _row: Adw.ActionRow) -> None:
        self._load_retention_values(self.service.cups_defaults())

    def _load_retention_values(self, settings: RetentionSettings) -> None:
        self.files_unlimited.set_active(settings.files_unlimited)
        if settings.files_days:
            self.files_days.set_value(settings.files_days)
        self.history_unlimited.set_active(settings.history_unlimited)
        if settings.history_days:
            self.history_days.set_value(settings.history_days)
        self.max_jobs_unlimited.set_active(settings.max_jobs_unlimited)
        if not settings.max_jobs_unlimited:
            self.max_jobs.set_value(settings.max_jobs)

    def _retention_loaded(self, settings: RetentionSettings) -> None:
        self._load_retention_values(settings)
        self._set_retention_sensitive(True)
        self._set_footer_status(
            self.retention_footer_status,
            _("Current CUPS values loaded. Only Apply saves changes."),
        )

    def _retention_failed(self, error: BaseException) -> None:
        self._set_retention_sensitive(False)
        self._set_footer_status(
            self.retention_footer_status,
            _("Could not load the current CUPS values."),
            str(error),
        )

    def _apply_retention(self, _button: Gtk.Button) -> None:
        if not self._retention_editor_enabled:
            return
        self._set_retention_sensitive(False)
        self.retention_apply_button.set_label(_("Applying…"))
        self._set_footer_status(
            self.retention_footer_status,
            _("Applying retention settings…"),
        )
        self.runner.submit(
            lambda: self.service.apply_retention_settings(
                files_days=(
                    None
                    if self.files_unlimited.get_active()
                    else int(self.files_days.get_value())
                ),
                history_days=(
                    None
                    if self.history_unlimited.get_active()
                    else int(self.history_days.get_value())
                ),
                max_jobs=(
                    None
                    if self.max_jobs_unlimited.get_active()
                    else int(self.max_jobs.get_value())
                ),
            ),
            self._retention_applied,
            self._retention_apply_failed,
        )

    def _retention_applied(self, _result: object) -> None:
        self.retention_apply_button.set_label(_("Restarting CUPS…"))
        self._set_footer_status(
            self.retention_footer_status,
            _("Restarting CUPS and confirming the connection…"),
        )
        self.wait_for_cups_restart(self, self._retention_restart_ready)

    def _retention_restart_ready(self) -> None:
        self.retention_apply_button.set_label(_("Apply"))
        show_message(self, _("Retention settings applied"), _("CUPS is now using the selected values."))
        self._set_footer_status(
            self.retention_footer_status,
            _("Reloading current CUPS values…"),
        )
        self.runner.submit(
            self.service.read_retention_settings,
            self._retention_loaded,
            self._retention_failed,
        )

    def _retention_apply_failed(self, error: BaseException) -> None:
        self.retention_apply_button.set_label(_("Apply"))
        self._set_retention_sensitive(True)
        self._set_footer_status(
            self.retention_footer_status,
            _("Could not apply the retention settings."),
            str(error),
        )
        show_message(self, _("Could not apply retention settings"), str(error))

    def _set_retention_sensitive(self, enabled: bool) -> None:
        self._retention_editor_enabled = enabled
        self.files_unlimited.set_sensitive(enabled)
        self.files_days.set_sensitive(enabled and not self.files_unlimited.get_active())
        self.history_unlimited.set_sensitive(enabled)
        self.history_days.set_sensitive(enabled and not self.history_unlimited.get_active())
        self.max_jobs_unlimited.set_sensitive(enabled)
        self.max_jobs.set_sensitive(enabled and not self.max_jobs_unlimited.get_active())
        self.retention_apply_button.set_sensitive(enabled)
        self.defaults_row.set_sensitive(enabled)

    def _server_loaded(self, settings: CupsServerSettings) -> None:
        self.web_interface.set_active(settings.web_interface)
        self.debug_logging.set_active(settings.debug_logging)
        self.remote_admin.set_active(settings.remote_admin)
        self.remote_any.set_active(settings.remote_any)
        self.share_printers.set_active(settings.share_printers)
        self.user_cancel_any.set_active(settings.user_cancel_any)
        self._set_server_sensitive(True)
        self._set_footer_status(
            self.server_footer_status,
            _("Current CUPS values loaded. Only Apply saves changes."),
        )

    def _server_failed(self, error: BaseException) -> None:
        self._set_server_sensitive(False)
        self._set_footer_status(
            self.server_footer_status,
            _("Could not load the current CUPS values."),
            str(error),
        )

    def _current_server_settings(self) -> CupsServerSettings:
        return CupsServerSettings(
            web_interface=self.web_interface.get_active(),
            debug_logging=self.debug_logging.get_active(),
            remote_admin=self.remote_admin.get_active(),
            remote_any=self.remote_any.get_active(),
            share_printers=self.share_printers.get_active(),
            user_cancel_any=self.user_cancel_any.get_active(),
        )

    def _apply_server(self, _button: Gtk.Button) -> None:
        if not self._server_editor_enabled:
            return
        settings = self._current_server_settings()
        if settings.remote_any:
            confirm(
                self,
                _("Allow CUPS connections from any network?"),
                _(
                    "This can expose shared printers or administration beyond the local subnet. "
                    "Continue only when the computer firewall and CUPS access policy are understood."
                ),
                _("Apply risky setting"),
                lambda: self._submit_server_settings(settings),
            )
            return
        self._submit_server_settings(settings)

    def _submit_server_settings(self, settings: CupsServerSettings) -> None:
        self._set_server_sensitive(False)
        self.server_apply_button.set_label(_("Applying…"))
        self._set_footer_status(
            self.server_footer_status,
            _("Applying global server settings…"),
        )
        self.runner.submit(
            lambda: self.service.apply_server_settings(settings),
            self._server_applied,
            self._server_apply_failed,
        )

    def _server_applied(self, _result: object) -> None:
        self.server_apply_button.set_label(_("Restarting CUPS…"))
        self._set_footer_status(
            self.server_footer_status,
            _("Restarting CUPS and confirming the connection…"),
        )
        self.wait_for_cups_restart(self, self._server_restart_ready)

    def _server_restart_ready(self) -> None:
        self.server_apply_button.set_label(_("Apply"))
        show_message(self, _("Global CUPS settings applied"), _("The print server is now using the selected switches."))
        self._set_footer_status(
            self.server_footer_status,
            _("Reloading current CUPS values…"),
        )
        self.runner.submit(
            self.service.read_server_settings,
            self._server_loaded,
            self._server_failed,
        )

    def _server_apply_failed(self, error: BaseException) -> None:
        self.server_apply_button.set_label(_("Apply"))
        self._set_server_sensitive(True)
        self._set_footer_status(
            self.server_footer_status,
            _("Could not apply the global server settings."),
            str(error),
        )
        show_message(self, _("Could not apply global server settings"), str(error))

    def _set_server_sensitive(self, enabled: bool) -> None:
        self._server_editor_enabled = enabled
        for row in (
            self.web_interface,
            self.debug_logging,
            self.remote_admin,
            self.remote_any,
            self.share_printers,
            self.user_cancel_any,
        ):
            row.set_sensitive(enabled)
        self.server_apply_button.set_sensitive(enabled)

    def _system_info_loaded(self, info: CupsSystemInfo) -> None:
        default = info.default_printer or _("none")
        self.system_info_row.set_title(_("CUPS {version} on {server}").format(version=info.version, server=info.server))
        self.system_info_row.set_subtitle(
            _("User: {user} · Default: {default} · {count} destinations").format(
                user=info.user or _("unknown"),
                default=default,
                count=info.printers,
            )
        )

    def _system_info_failed(self, error: BaseException) -> None:
        self.system_info_row.set_title(_("Could not read CUPS service information"))
        self.system_info_row.set_subtitle(str(error))

    def _open_cups_web(self, _row: Adw.ActionRow) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri("http://localhost:631", None)
        except Exception as error:
            show_message(self, _("Could not open the CUPS web interface"), str(error))

    def _confirm_clear(self, _row: Adw.ActionRow) -> None:
        confirm(
            self,
            _("Delete all print history?"),
            _("This permanently removes retained spool files and job metadata. It cannot be undone."),
            _("Delete all"),
            self._clear_history,
        )

    def _clear_history(self) -> None:
        self.runner.submit(
            self.service.purge_all_jobs,
            self._history_cleared,
            lambda error: show_message(self, _("Could not delete all history"), str(error)),
        )

    def _history_cleared(self, count: int) -> None:
        show_message(
            self,
            _("Print history deleted"),
            _("{count} jobs were permanently removed.").format(count=count),
        )
        self.on_history_changed()
