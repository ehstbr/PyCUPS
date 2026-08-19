from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from .. import APP_ID, APP_NAME, APP_TAGLINE
from ..core.onboarding import (
    SUGGESTED_RETENTION,
    OnboardingStateStore,
)
from ..models import RetentionSettings
from ..util.async_runner import AsyncRunner
from ..util.i18n import _
from .dialogs import show_message


PROJECT_URL = "https://github.com/ehstbr/PyCUPS"


def _spin_row(title: str, lower: int, upper: int, value: int) -> Adw.SpinRow:
    return Adw.SpinRow(
        title=title,
        adjustment=Gtk.Adjustment(
            value=value,
            lower=lower,
            upper=upper,
            step_increment=1,
            page_increment=10,
        ),
    )


class OnboardingWindow(Adw.ApplicationWindow):
    """Three-step, explicitly non-mutating first-run introduction."""

    def __init__(
        self,
        application: Gtk.Application,
        service: object,
        runner: AsyncRunner,
        state_store: OnboardingStateStore,
        *,
        parent: Gtk.Window | None,
        wait_for_cups_restart: Callable[
            [Gtk.Window, Callable[[], object]],
            None,
        ],
        on_finish: Callable[[OnboardingWindow, bool], None],
        on_close: Callable[[OnboardingWindow], None],
    ) -> None:
        super().__init__(
            application=application,
            title=_("Welcome to {app_name}").format(app_name=APP_NAME),
        )
        self.set_default_size(760, 720)
        self.set_resizable(True)
        if parent is not None:
            self.set_transient_for(parent)
            self.set_modal(True)

        self.service = service
        self.runner = runner
        self.state_store = state_store
        self.wait_for_cups_restart = wait_for_cups_restart
        self._on_finish = on_finish
        self._on_close = on_close
        self._page_name = "welcome"
        self._retention_loaded = False
        self._applying = False
        self._finishing = False
        self._closed = False
        self._settings_applied = False

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.window_title = Adw.WindowTitle(
            title=_("Welcome to {app_name}").format(app_name=APP_NAME),
            subtitle=_("Step 1 of 3"),
        )
        header.set_title_widget(self.window_title)
        toolbar.add_top_bar(header)

        self.pages = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
            transition_duration=250,
            vexpand=True,
        )
        self.pages.add_named(self._build_welcome_page(), "welcome")
        self.pages.add_named(self._build_retention_page(), "retention")
        self.pages.add_named(self._build_finish_page(), "finish")
        toolbar.set_content(self.pages)

        footer = Gtk.Box(spacing=10)
        footer.set_margin_top(10)
        footer.set_margin_bottom(10)
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        self.back_button = Gtk.Button(label=_("Back"))
        self.back_button.connect("clicked", self._go_back)
        footer.append(self.back_button)
        footer.append(Gtk.Box(hexpand=True))
        self.skip_button = Gtk.Button(label=_("Skip without changes"))
        self.skip_button.connect("clicked", self._skip_retention)
        footer.append(self.skip_button)
        self.next_button = Gtk.Button(css_classes=["suggested-action"])
        self.next_button.connect("clicked", self._go_forward)
        footer.append(self.next_button)
        toolbar.add_bottom_bar(footer)

        self.set_content(toolbar)
        self.connect("close-request", self._close_requested)
        self._set_proposed_values()
        self._set_page("welcome")
        self._load_current_values()

    @staticmethod
    def _page_scroller(content: Gtk.Widget) -> Gtk.ScrolledWindow:
        scroller = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        clamp = Adw.Clamp(maximum_size=680, tightening_threshold=520)
        clamp.set_child(content)
        scroller.set_child(clamp)
        return scroller

    @staticmethod
    def _page_box() -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        return box

    @staticmethod
    def _compact_hero(
        icon_name: str,
        title: str,
        description: str,
    ) -> tuple[Gtk.Box, Gtk.Label]:
        """Build a compact hero that never introduces its own scroller."""

        hero = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            halign=Gtk.Align.FILL,
        )
        hero.set_margin_top(2)
        hero.set_margin_bottom(4)
        hero.append(Gtk.Image(icon_name=icon_name, pixel_size=72))
        hero.append(
            Gtk.Label(
                label=title,
                css_classes=["title-1"],
                justify=Gtk.Justification.CENTER,
                wrap=True,
                xalign=0.5,
            )
        )
        description_label = Gtk.Label(
            label=description,
            css_classes=["dim-label"],
            justify=Gtk.Justification.CENTER,
            wrap=True,
            xalign=0.5,
            max_width_chars=72,
        )
        hero.append(description_label)
        return hero, description_label

    def _build_welcome_page(self) -> Gtk.Widget:
        content = self._page_box()
        hero, _description = self._compact_hero(
            APP_ID,
            _("Welcome to {app_name}").format(app_name=APP_NAME),
            _(
                "{tagline} helps you find, preview, export, and reprint documents retained by CUPS."
            ).format(tagline=APP_TAGLINE),
        )
        content.append(hero)

        privacy = Adw.PreferencesGroup(title=_("Privacy and transparency"))
        privacy.add(
            Adw.ActionRow(
                title=_("Your print documents stay on this computer"),
                subtitle=_(
                    "PyCUPS never uploads retained print files or job metadata to the internet."
                ),
                icon_name="security-high-symbolic",
            )
        )
        privacy.add(
            Adw.ActionRow(
                title=_("Only automatic internet access: update checks"),
                subtitle=_(
                    "A small version manifest is read from GitHub. No print content is included."
                ),
                icon_name="software-update-available-symbolic",
            )
        )
        source = Adw.ActionRow(
            title=_("Open-source software"),
            subtitle=_("Inspect the complete source code and report issues on GitHub."),
            icon_name="text-x-script-symbolic",
            activatable=True,
        )
        source.add_suffix(Gtk.Image(icon_name="adw-external-link-symbolic"))
        source.connect("activated", self._open_source)
        privacy.add(source)
        content.append(privacy)

        local = Adw.PreferencesGroup()
        local.add(
            Adw.ActionRow(
                title=_("CUPS remains in control"),
                subtitle=_(
                    "The next step only proposes retention values. Nothing changes without your explicit approval and administrator authorization."
                ),
                icon_name="dialog-information-symbolic",
            )
        )
        content.append(local)
        return self._page_scroller(content)

    def _build_retention_page(self) -> Gtk.Widget:
        content = self._page_box()

        introduction = Adw.PreferencesGroup(
            title=_("A balanced retention starting point"),
            description=_(
                "Thirty days of print files keeps recent documents reprintable. Ninety days of history preserves useful metadata, while both time limits avoid retaining information indefinitely. MaxJobs is unlimited so a job-count cap cannot shorten those periods."
            ),
        )
        introduction.add(
            Adw.ActionRow(
                title=_("Suggested: files 30 days · history 90 days · job count unlimited"),
                subtitle=_(
                    "These are editable suggestions, not defaults applied by installation or startup."
                ),
                icon_name="emblem-default-symbolic",
            )
        )
        content.append(introduction)

        current = Adw.PreferencesGroup(title=_("Current CUPS configuration"))
        self.current_files = Adw.ActionRow(
            title=_("Retained print files"),
            subtitle=_("Loading…"),
        )
        self.current_history = Adw.ActionRow(
            title=_("Job history"),
            subtitle=_("Loading…"),
        )
        self.current_max_jobs = Adw.ActionRow(
            title=_("Job-count limit"),
            subtitle=_("Loading…"),
        )
        current.add(self.current_files)
        current.add(self.current_history)
        current.add(self.current_max_jobs)
        content.append(current)

        proposed = Adw.PreferencesGroup(
            title=_("Proposed configuration"),
            description=_("Edit any value before applying it to the global CUPS service."),
        )
        self.files_unlimited = Adw.SwitchRow(
            title=_("No time limit for retained files"),
            subtitle="PreserveJobFiles=Yes",
        )
        self.files_unlimited.connect("notify::active", self._proposal_mode_changed)
        proposed.add(self.files_unlimited)
        self.files_days = _spin_row(_("Otherwise keep files for (days)"), 1, 3650, 30)
        proposed.add(self.files_days)

        self.history_unlimited = Adw.SwitchRow(
            title=_("No time limit for history"),
            subtitle="PreserveJobHistory=Yes",
        )
        self.history_unlimited.connect("notify::active", self._proposal_mode_changed)
        proposed.add(self.history_unlimited)
        self.history_days = _spin_row(_("Otherwise keep history for (days)"), 1, 3650, 90)
        proposed.add(self.history_days)

        self.max_jobs_unlimited = Adw.SwitchRow(
            title=_("Unlimited number of jobs"),
            subtitle="MaxJobs=0",
        )
        self.max_jobs_unlimited.connect("notify::active", self._proposal_mode_changed)
        proposed.add(self.max_jobs_unlimited)
        self.max_jobs = _spin_row(_("Otherwise keep at most"), 1, 1_000_000, 500)
        proposed.add(self.max_jobs)
        content.append(proposed)

        actions = Adw.PreferencesGroup()
        restore = Adw.ActionRow(
            title=_("Restore the suggested values"),
            subtitle=_("Files: 30 days · History: 90 days · MaxJobs: unlimited"),
            icon_name="edit-undo-symbolic",
            activatable=True,
        )
        restore.connect("activated", lambda _row: self._set_proposed_values())
        actions.add(restore)
        self.reload_row = Adw.ActionRow(
            title=_("Reload current CUPS values"),
            subtitle=_("The proposed fields are not changed."),
            icon_name="view-refresh-symbolic",
            activatable=True,
        )
        self.reload_row.connect("activated", lambda _row: self._load_current_values())
        actions.add(self.reload_row)
        content.append(actions)
        return self._page_scroller(content)

    def _build_finish_page(self) -> Gtk.Widget:
        content = self._page_box()
        finish_hero, self.finish_description = self._compact_hero(
            "emblem-ok-symbolic",
            _("Setup complete"),
            _(
                "PyCUPS is ready. No CUPS setting is changed until you explicitly apply it."
            ),
        )
        content.append(finish_hero)
        summary = Adw.PreferencesGroup(title=_("What happens next"))
        self.finish_summary = Adw.ActionRow(
            title=_("No retention changes were made"),
            subtitle=_("You can configure them later in Settings › Retention."),
            icon_name="dialog-information-symbolic",
        )
        summary.add(self.finish_summary)
        summary.add(
            Adw.ActionRow(
                title=_("Your print history will now open"),
                subtitle=_(
                    "The welcome setup can be opened again at any time from the main menu."
                ),
                icon_name="go-next-symbolic",
            )
        )
        content.append(summary)
        return self._page_scroller(content)

    def _set_page(self, name: str) -> None:
        self._page_name = name
        self.pages.set_visible_child_name(name)
        if name == "welcome":
            self.window_title.set_subtitle(_("Step 1 of 3"))
            self.back_button.set_visible(False)
            self.skip_button.set_visible(False)
            self.next_button.set_label(_("Continue"))
            self.next_button.set_sensitive(True)
        elif name == "retention":
            self.window_title.set_subtitle(_("Step 2 of 3"))
            self.back_button.set_visible(True)
            self.skip_button.set_visible(True)
            self.next_button.set_label(_("Apply and continue"))
            self.next_button.set_sensitive(self._retention_loaded and not self._applying)
        else:
            self.window_title.set_subtitle(_("Step 3 of 3"))
            self.back_button.set_visible(False)
            self.skip_button.set_visible(False)
            self.next_button.set_label(
                _("Start using {app_name}").format(app_name=APP_NAME)
            )
            self.next_button.set_sensitive(True)

    def _go_back(self, _button: Gtk.Button) -> None:
        if self._page_name == "retention" and not self._applying:
            self._set_page("welcome")

    def _go_forward(self, _button: Gtk.Button) -> None:
        if self._page_name == "welcome":
            self._set_page("retention")
        elif self._page_name == "retention":
            self._apply_retention()
        else:
            self._finish()

    def _skip_retention(self, _button: Gtk.Button) -> None:
        if self._applying:
            return
        self._settings_applied = False
        self.finish_description.set_label(
            _("No CUPS settings were changed. You can adjust retention later in Settings.")
        )
        self.finish_summary.set_title(_("Retention configuration was skipped"))
        self.finish_summary.set_subtitle(
            _("The current CUPS values remain exactly as they were.")
        )
        self._set_page("finish")

    def _set_proposed_values(self) -> None:
        self.files_unlimited.set_active(False)
        self.files_days.set_value(SUGGESTED_RETENTION.files_days)
        self.history_unlimited.set_active(False)
        self.history_days.set_value(SUGGESTED_RETENTION.history_days)
        self.max_jobs_unlimited.set_active(SUGGESTED_RETENTION.max_jobs is None)
        if SUGGESTED_RETENTION.max_jobs is not None:
            self.max_jobs.set_value(SUGGESTED_RETENTION.max_jobs)
        self._proposal_mode_changed()

    def _proposal_mode_changed(self, *_args: object) -> None:
        enabled = self._retention_loaded and not self._applying
        self.files_days.set_sensitive(enabled and not self.files_unlimited.get_active())
        self.history_days.set_sensitive(enabled and not self.history_unlimited.get_active())
        self.max_jobs.set_sensitive(enabled and not self.max_jobs_unlimited.get_active())

    def _set_editor_sensitive(self, enabled: bool) -> None:
        for row in (
            self.files_unlimited,
            self.history_unlimited,
            self.max_jobs_unlimited,
            self.reload_row,
        ):
            row.set_sensitive(enabled)
        self._proposal_mode_changed()
        if self._page_name == "retention":
            self.next_button.set_sensitive(enabled)
            self.skip_button.set_sensitive(not self._applying)
            self.back_button.set_sensitive(not self._applying)

    def _load_current_values(self) -> None:
        if self._applying:
            return
        self._retention_loaded = False
        self.current_files.set_subtitle(_("Loading…"))
        self.current_history.set_subtitle(_("Loading…"))
        self.current_max_jobs.set_subtitle(_("Loading…"))
        self.reload_row.set_sensitive(False)
        self._set_editor_sensitive(False)
        self.runner.submit(
            self.service.read_retention_settings,
            self._current_values_loaded,
            self._current_values_failed,
        )

    def _current_values_loaded(self, settings: RetentionSettings) -> None:
        if self._closed or self._page_name == "finish":
            return
        self._retention_loaded = True
        self.current_files.set_subtitle(
            self._duration_text(
                settings.preserve_files,
                settings.files_days,
                settings.files_unlimited,
            )
        )
        self.current_history.set_subtitle(
            self._duration_text(
                settings.preserve_history,
                settings.history_days,
                settings.history_unlimited,
            )
        )
        self.current_max_jobs.set_subtitle(
            _("Unlimited (MaxJobs=0)")
            if settings.max_jobs_unlimited
            else _("{count} jobs").format(count=settings.max_jobs)
        )
        self._set_editor_sensitive(True)

    def _current_values_failed(self, error: BaseException) -> None:
        if self._closed or self._page_name == "finish":
            return
        self._retention_loaded = False
        message = _("Could not read the current value")
        self.current_files.set_subtitle(message)
        self.current_history.set_subtitle(message)
        self.current_max_jobs.set_subtitle(message)
        self._set_editor_sensitive(False)
        self.reload_row.set_sensitive(True)
        self.skip_button.set_sensitive(True)
        show_message(
            self,
            _("Could not load the current CUPS values"),
            str(error),
        )

    @staticmethod
    def _duration_text(raw: str, days: int | None, unlimited: bool) -> str:
        if unlimited:
            return _("No time limit")
        if raw.strip().lower() in {"no", "false", "off", "0"}:
            return _("Not retained")
        if days == 1:
            return _("1 day")
        if days is not None:
            return _("{days} days").format(days=days)
        return raw

    def _apply_retention(self) -> None:
        if not self._retention_loaded or self._applying:
            return
        self._applying = True
        self.set_deletable(False)
        self.next_button.set_label(_("Applying…"))
        self._set_editor_sensitive(False)
        values = self._proposed_values()
        self.runner.submit(
            lambda: self.service.apply_retention_settings(**values),
            lambda _result: self._retention_applied(values),
            self._retention_apply_failed,
        )

    def _proposed_values(self) -> dict[str, int | None]:
        return {
            "files_days": (
                None
                if self.files_unlimited.get_active()
                else int(self.files_days.get_value())
            ),
            "history_days": (
                None
                if self.history_unlimited.get_active()
                else int(self.history_days.get_value())
            ),
            "max_jobs": (
                None
                if self.max_jobs_unlimited.get_active()
                else int(self.max_jobs.get_value())
            ),
        }

    def _retention_applied(self, values: dict[str, int | None]) -> None:
        if self._closed:
            return
        self._settings_applied = True
        self.finish_description.set_label(
            _("The retention values were saved. Waiting for CUPS to become available again.")
        )
        self.finish_summary.set_title(_("Retention configuration saved"))
        self.finish_summary.set_subtitle(self._proposal_summary(values))
        self._set_page("finish")
        self.next_button.set_label(_("Restarting CUPS…"))
        self.next_button.set_sensitive(False)
        self.wait_for_cups_restart(
            self,
            lambda: self._retention_restart_ready(values),
        )

    def _retention_restart_ready(self, values: dict[str, int | None]) -> None:
        if self._closed:
            return
        self._applying = False
        self.set_deletable(True)
        self.finish_description.set_label(
            _("The selected retention values were applied to CUPS successfully.")
        )
        self.finish_summary.set_title(_("Retention configuration applied"))
        self.finish_summary.set_subtitle(self._proposal_summary(values))
        self._set_page("finish")

    def _retention_apply_failed(self, error: BaseException) -> None:
        if self._closed:
            return
        self._applying = False
        self.set_deletable(True)
        self.next_button.set_label(_("Apply and continue"))
        self._set_editor_sensitive(True)
        show_message(
            self,
            _("Could not apply retention settings"),
            str(error),
        )

    @staticmethod
    def _proposal_summary(values: dict[str, int | None]) -> str:
        files = (
            _("no time limit")
            if values["files_days"] is None
            else _("{days} days").format(days=values["files_days"])
        )
        history = (
            _("no time limit")
            if values["history_days"] is None
            else _("{days} days").format(days=values["history_days"])
        )
        jobs = (
            _("unlimited")
            if values["max_jobs"] is None
            else str(values["max_jobs"])
        )
        return _("Files: {files} · History: {history} · MaxJobs: {jobs}").format(
            files=files,
            history=history,
            jobs=jobs,
        )

    def _finish(self) -> None:
        try:
            self.state_store.mark_complete()
        except OSError as error:
            show_message(
                self,
                _("Could not save the welcome status"),
                str(error),
            )
            return
        self._finishing = True
        self._on_finish(self, self._settings_applied)

    def _open_source(self, _row: Adw.ActionRow) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(PROJECT_URL, None)
        except Exception as error:
            show_message(self, _("Could not open the project website"), str(error))

    def _close_requested(self, _window: Gtk.Window) -> bool:
        self._closed = True
        if not self._finishing:
            self._on_close(self)
        return False
