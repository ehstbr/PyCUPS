from __future__ import annotations

import threading
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gio, GLib, Gtk

from . import APP_ID, APP_NAME
from .core.cups_service import CupsService, CupsServiceError
from .core.onboarding import OnboardingStateStore
from .core.updates import UpdateCheckResult, UpdateChecker, UpdateManifest
from .core.window_presentation import MappedWindowPresenter
from .ui.main_window import MainWindow
from .ui.onboarding import OnboardingWindow
from .ui.cups_restart import CupsRestartWindow
from .ui.update_window import UpdateWindow
from .util.async_runner import AsyncRunner
from .util.i18n import _
from .util.i18n import setup_gettext


class PrintArchiveApplication(Adw.Application):
    def __init__(self) -> None:
        setup_gettext()
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.service: CupsService | None = None
        self.runner: AsyncRunner | None = None
        self.window: MainWindow | None = None
        self.onboarding_window: OnboardingWindow | None = None
        self.cups_restart_window: CupsRestartWindow | None = None
        self.update_window: UpdateWindow | None = None
        self.onboarding_state = OnboardingStateStore()
        self.update_checker = UpdateChecker()
        self._startup_update_complete = False
        self._startup_update_in_progress = False
        self._manual_update_in_progress = False
        self._mandatory_update_manifest: UpdateManifest | None = None
        self._pending_startup_update: UpdateManifest | None = None
        self._startup_hold = False
        self._cups_restart_on_ready: Callable[[], object] | None = None
        self._cups_restart_cancel: threading.Event | None = None
        self._cups_restart_wait_active = False
        self._cups_restart_retry_source: int | None = None
        self._cups_restart_blocked_windows: list[tuple[Gtk.Window, bool, bool]] = []
        self._cups_restart_blocked_actions: dict[str, bool] = {}
        self._shutting_down = False
        self._update_window_presenter = MappedWindowPresenter(
            idle_add=GLib.idle_add,
            show=lambda manifest, parent: self._show_update_window(manifest, parent=parent),
            source_remove=GLib.SOURCE_REMOVE,
        )

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        for name, callback in (
            ("refresh", lambda *_args: self.window and self.window.refresh()),
            ("settings", lambda *_args: self._show_settings()),
            ("onboarding", lambda *_args: self._show_onboarding(force=True)),
            ("about", lambda *_args: self.window and self.window.show_about()),
            ("check-update", lambda *_args: self.check_for_updates(self.get_active_window())),
            ("quit", lambda *_args: self.quit()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        self.set_accels_for_action("app.refresh", ["<Primary>r"])
        self.set_accels_for_action("app.settings", ["<Primary>comma"])
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def do_activate(self) -> None:
        if self.cups_restart_window is not None:
            self.cups_restart_window.present()
            return
        if self._mandatory_update_manifest:
            self._show_update_window(self._mandatory_update_manifest)
            return
        if not self._startup_update_complete:
            self._begin_startup_update_check()
            return
        self._continue_activation()

    def _begin_startup_update_check(self) -> None:
        if self._startup_update_in_progress:
            return
        self._startup_update_in_progress = True
        self.hold()
        self._startup_hold = True
        try:
            self.update_checker.check(self._startup_update_finished)
        except Exception as error:
            self._startup_update_finished(UpdateCheckResult(error=str(error)))

    def _startup_update_finished(self, result: UpdateCheckResult) -> None:
        self._startup_update_in_progress = False
        self._startup_update_complete = True
        if result.update_available and result.latest and result.latest.mandatory:
            self._enter_mandatory_update_mode(result.latest)
            self._release_startup_hold()
            return
        self._continue_activation()
        self._release_startup_hold()
        if result.update_available and result.latest:
            if self.onboarding_window is not None:
                self._pending_startup_update = result.latest
            else:
                self._queue_update_window_for_mapped_parent(result.latest, self.window)
        # Automatic network/manifest failures deliberately fail open and stay silent.

    def _release_startup_hold(self) -> None:
        if self._startup_hold:
            self._startup_hold = False
            self.release()

    def _continue_activation(self) -> None:
        if self._mandatory_update_manifest:
            self._show_update_window(self._mandatory_update_manifest)
            return
        if self.runner is None:
            self.runner = AsyncRunner(GLib.idle_add)
        if self.service is None:
            try:
                self.service = CupsService()
            except CupsServiceError as error:
                if self.window is None:
                    self.window = MainWindow(self, None, self.runner, startup_error=str(error))
                self.window.present()
                return
        if self.onboarding_window is not None:
            self.onboarding_window.present()
            return
        if self.window is None and not self.onboarding_state.is_complete():
            self._show_onboarding()
            return
        self._show_main_window()

    def _show_main_window(self) -> None:
        if self.cups_restart_window is not None:
            self.cups_restart_window.present()
            return
        if self.runner is None or self.service is None:
            return
        if self.window is None:
            self.window = MainWindow(self, self.service, self.runner)
        self.window.unminimize()
        self.window.present()

    def _show_onboarding(self, *, force: bool = False) -> None:
        if self.cups_restart_window is not None:
            self.cups_restart_window.present()
            return
        if self._mandatory_update_manifest:
            self._show_update_window(self._mandatory_update_manifest)
            return
        if not force and self.onboarding_state.is_complete():
            self._show_main_window()
            return
        if self.runner is None or self.service is None:
            return
        if self.onboarding_window is not None:
            self.onboarding_window.unminimize()
            self.onboarding_window.present()
            return
        active = self.get_active_window()
        parent = (
            active
            if active is not None
            and active is not self.update_window
            and active is not self.onboarding_window
            else self.window
        )
        self.onboarding_window = OnboardingWindow(
            self,
            self.service,
            self.runner,
            self.onboarding_state,
            parent=parent,
            wait_for_cups_restart=self.wait_for_cups_restart,
            on_finish=self._onboarding_finished,
            on_close=self._onboarding_closed,
        )
        self.onboarding_window.present()

    def _onboarding_finished(
        self,
        window: OnboardingWindow,
        settings_changed: bool,
    ) -> None:
        if self.onboarding_window is not window:
            return
        needs_main_window = self.window is None
        self.onboarding_window = None
        window.close()
        if needs_main_window:
            self._show_main_window()
        if settings_changed and self.window is not None:
            self.window.refresh()
        if self._pending_startup_update is not None:
            manifest = self._pending_startup_update
            self._pending_startup_update = None
            self._queue_update_window_for_mapped_parent(manifest, self.window)

    def _onboarding_closed(self, window: OnboardingWindow) -> None:
        if self.onboarding_window is window:
            self.onboarding_window = None

    def _show_settings(self) -> None:
        if self.cups_restart_window is not None:
            self.cups_restart_window.present()
        elif self._mandatory_update_manifest:
            self._show_update_window(self._mandatory_update_manifest)
        elif self.window:
            self.window.show_settings()

    def wait_for_cups_restart(
        self,
        parent: Gtk.Window,
        on_ready: Callable[[], object],
    ) -> None:
        """Block every application window until fresh CUPS probes are stable."""

        if self.cups_restart_window is not None:
            self.cups_restart_window.present()
            return
        if self.runner is None or self.service is None:
            raise RuntimeError("CUPS restart wait requires an initialized service.")

        self._cups_restart_on_ready = on_ready
        self.cups_restart_window = CupsRestartWindow(
            self,
            parent,
            on_retry=self._retry_cups_restart,
            on_quit=self.quit,
        )
        self.cups_restart_window.present()
        self._set_cups_restart_blocked(True)
        self._retry_cups_restart()

    def _retry_cups_restart(self) -> None:
        if self._cups_restart_retry_source is not None:
            GLib.source_remove(self._cups_restart_retry_source)
            self._cups_restart_retry_source = None
        if (
            self._shutting_down
            or self._cups_restart_wait_active
            or self.cups_restart_window is None
            or self.runner is None
            or self.service is None
        ):
            return
        self.cups_restart_window.show_waiting()
        cancel_event = threading.Event()
        self._cups_restart_cancel = cancel_event
        self._cups_restart_wait_active = True
        self.runner.submit(
            lambda: self.service.wait_for_cups_ready(cancel_event=cancel_event),
            lambda _result: self._cups_restart_ready(cancel_event),
            lambda error: self._cups_restart_failed(cancel_event, error),
        )

    def _cups_restart_ready(self, cancel_event: threading.Event) -> None:
        if self._shutting_down or self._cups_restart_cancel is not cancel_event:
            return
        self._cups_restart_wait_active = False
        self._cancel_cups_restart_retry()
        callback = self._cups_restart_on_ready
        self._set_cups_restart_blocked(False)
        if callback is not None:
            callback()

    def _cups_restart_failed(
        self,
        cancel_event: threading.Event,
        error: BaseException,
    ) -> None:
        if self._shutting_down or self._cups_restart_cancel is not cancel_event:
            return
        self._cups_restart_wait_active = False
        if self.cups_restart_window is not None:
            self.cups_restart_window.show_failure(error)
            self._cups_restart_retry_source = GLib.timeout_add_seconds(
                1,
                self._continue_cups_restart_wait,
            )

    def _continue_cups_restart_wait(self) -> bool:
        self._cups_restart_retry_source = None
        if self._shutting_down or self.cups_restart_window is None:
            return GLib.SOURCE_REMOVE
        self._retry_cups_restart()
        return GLib.SOURCE_REMOVE

    def _cancel_cups_restart_retry(self) -> None:
        if self._cups_restart_retry_source is not None:
            GLib.source_remove(self._cups_restart_retry_source)
            self._cups_restart_retry_source = None

    def _set_cups_restart_blocked(self, blocked: bool) -> None:
        action_names = (
            "refresh",
            "settings",
            "onboarding",
            "about",
            "check-update",
            "quit",
        )
        if blocked:
            if self.window is not None:
                self.window.set_cups_restart_in_progress(True)
            self._cups_restart_blocked_actions.clear()
            for name in action_names:
                action = self.lookup_action(name)
                if isinstance(action, Gio.SimpleAction):
                    self._cups_restart_blocked_actions[name] = action.get_enabled()
                    action.set_enabled(False)
            self._cups_restart_blocked_windows.clear()
            for window in self.get_windows():
                if window is self.cups_restart_window:
                    continue
                self._cups_restart_blocked_windows.append(
                    (window, window.get_sensitive(), window.get_deletable())
                )
                window.set_deletable(False)
                window.set_sensitive(False)
            return

        dialog = self.cups_restart_window
        self._cancel_cups_restart_retry()
        self.cups_restart_window = None
        if dialog is not None:
            dialog.close_when_ready()
        for window, was_sensitive, was_deletable in self._cups_restart_blocked_windows:
            window.set_sensitive(was_sensitive)
            window.set_deletable(was_deletable)
        self._cups_restart_blocked_windows.clear()
        for name, was_enabled in self._cups_restart_blocked_actions.items():
            action = self.lookup_action(name)
            if isinstance(action, Gio.SimpleAction):
                action.set_enabled(was_enabled)
        self._cups_restart_blocked_actions.clear()
        self._cups_restart_cancel = None
        self._cups_restart_on_ready = None
        if self.window is not None:
            self.window.set_cups_restart_in_progress(False)

    def check_for_updates(self, parent: Gtk.Window | None = None) -> None:
        if self.cups_restart_window is not None:
            self.cups_restart_window.present()
            return
        if self._mandatory_update_manifest:
            self._show_update_window(self._mandatory_update_manifest)
            return
        if self._manual_update_in_progress:
            return
        self._manual_update_in_progress = True
        progress = Adw.AlertDialog(
            heading=_("Checking for Updates"),
            body=_("Contacting the GitHub version service…"),
        )
        progress.present(parent)

        def finished(result: UpdateCheckResult) -> None:
            self._manual_update_in_progress = False
            progress.close()
            if result.error:
                self._show_status_dialog(
                    _("Could Not Check for Updates"),
                    _(
                        "The version information could not be obtained. "
                        "Check your connection and try again later."
                    ),
                    parent,
                )
                return
            if result.update_available and result.latest:
                if result.latest.mandatory:
                    self._enter_mandatory_update_mode(result.latest)
                else:
                    self._show_update_window(result.latest, parent=parent)
                return
            self._show_status_dialog(
                _("{app_name} Is Up to Date").format(app_name=APP_NAME),
                _("You are already using the latest available version."),
                parent,
            )

        try:
            self.update_checker.check(finished)
        except Exception as error:
            finished(UpdateCheckResult(error=str(error)))

    def _show_status_dialog(self, heading: str, body: str, parent: Gtk.Window | None) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("close", _("Close"))
        dialog.set_default_response("close")

        def chosen(source: Adw.AlertDialog, result: Gio.AsyncResult) -> None:
            source.choose_finish(result)

        dialog.choose(parent, None, chosen)

    def _enter_mandatory_update_mode(self, manifest: UpdateManifest) -> None:
        self._mandatory_update_manifest = manifest
        self._pending_startup_update = None
        self._update_window_presenter.clear()
        if self.onboarding_window:
            onboarding = self.onboarding_window
            self.onboarding_window = None
            onboarding.close()
        if self.window:
            if self.window.settings_window:
                self.window.settings_window.close()
            self.window.close()
            self.window = None
        self._show_update_window(manifest)

    def _show_update_window(
        self,
        manifest: UpdateManifest,
        *,
        parent: Gtk.Window | None = None,
    ) -> None:
        if parent is None:
            parent = self._update_window_parent(require_mapped=True)
        elif not parent.get_mapped():
            parent = None
        if self.update_window:
            same_manifest = self.update_window.manifest == manifest
            same_parent = self.update_window.get_transient_for() is parent
            if (same_manifest and same_parent) or self.update_window.mandatory:
                self._present_update_window_foreground(self.update_window)
                return
            old_window = self.update_window
            self.update_window = None
            old_window.close()
        self.update_window = UpdateWindow(
            self,
            manifest,
            parent=parent,
            on_close=self._update_window_closed,
            on_quit=self.quit,
        )
        self.update_window.present()
        GLib.idle_add(self._present_update_window_foreground, self.update_window)

    def _queue_update_window_for_mapped_parent(
        self,
        manifest: UpdateManifest,
        parent: Gtk.Window | None = None,
    ) -> None:
        self._update_window_presenter.clear()
        parent = parent or self._update_window_parent()
        if parent is None:
            self._show_update_window(manifest)
            return
        self._update_window_presenter.queue(manifest, parent)

    def _update_window_parent(self, *, require_mapped: bool = False) -> Gtk.Window | None:
        candidates = (self.get_active_window(), self.onboarding_window, self.window)
        for candidate in candidates:
            if (
                candidate
                and candidate is not self.update_window
                and candidate.get_visible()
                and (not require_mapped or candidate.get_mapped())
            ):
                return candidate
        return None

    def _present_update_window_foreground(self, window: UpdateWindow) -> bool:
        if self.update_window is not window:
            return GLib.SOURCE_REMOVE
        window.unminimize()
        window.present()
        return GLib.SOURCE_REMOVE

    def _update_window_closed(self, window: UpdateWindow) -> None:
        if self.update_window is window:
            self.update_window = None

    def do_shutdown(self) -> None:
        self._shutting_down = True
        self._cancel_cups_restart_retry()
        if self._cups_restart_cancel is not None:
            self._cups_restart_cancel.set()
        if self.cups_restart_window is not None:
            self.cups_restart_window.close_when_ready()
            self.cups_restart_window = None
        self._update_window_presenter.clear()
        self.update_checker.cancel()
        if self.runner is not None:
            self.runner.shutdown()
        if self.service is not None:
            self.service.close()
        self.onboarding_window = None
        self._release_startup_hold()
        Adw.Application.do_shutdown(self)
