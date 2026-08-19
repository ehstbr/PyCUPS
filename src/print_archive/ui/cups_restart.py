from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ..util.i18n import _


class CupsRestartWindow(Adw.Window):
    """Non-dismissible application-wide CUPS readiness progress window."""

    def __init__(
        self,
        application: Gtk.Application,
        parent: Gtk.Window,
        *,
        on_retry: Callable[[], object],
        on_quit: Callable[[], object],
    ) -> None:
        super().__init__(
            application=application,
            transient_for=parent,
            modal=True,
            title=_("Restarting CUPS…"),
        )
        self.set_default_size(440, 300)
        self.set_resizable(False)
        self.set_deletable(False)
        self._closing_allowed = False
        self._on_retry = on_retry
        self._on_quit = on_quit
        self.connect("close-request", self._close_requested)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        header.set_title_widget(Adw.WindowTitle(title=_("CUPS service")))
        toolbar.add_top_bar(header)

        clamp = Adw.Clamp(maximum_size=420, tightening_threshold=320)
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
        )
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        self.visual = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=150,
            halign=Gtk.Align.CENTER,
        )
        self.spinner = Gtk.Spinner(
            spinning=True,
            width_request=48,
            height_request=48,
        )
        self.visual.add_named(self.spinner, "waiting")
        warning = Gtk.Image(
            icon_name="dialog-warning-symbolic",
            pixel_size=48,
            css_classes=["warning"],
        )
        self.visual.add_named(warning, "failure")
        content.append(self.visual)

        self.heading = Gtk.Label(
            label=_("Restarting CUPS…"),
            css_classes=["title-2"],
            justify=Gtk.Justification.CENTER,
            wrap=True,
        )
        content.append(self.heading)
        self.description = Gtk.Label(
            label=_(
                "Waiting for the local print service to become available again. "
                "PyCUPS will continue automatically after the connection is confirmed."
            ),
            css_classes=["dim-label"],
            justify=Gtk.Justification.CENTER,
            wrap=True,
            xalign=0.5,
        )
        content.append(self.description)
        self.detail = Gtk.Label(
            visible=False,
            css_classes=["dim-label", "caption"],
            justify=Gtk.Justification.CENTER,
            wrap=True,
            selectable=True,
            xalign=0.5,
        )
        content.append(self.detail)

        self.actions = Gtk.Box(
            spacing=10,
            halign=Gtk.Align.CENTER,
            visible=False,
        )
        retry = Gtk.Button(
            label=_("Try again"),
            css_classes=["suggested-action"],
        )
        retry.connect("clicked", lambda _button: self._retry())
        self.actions.append(retry)
        close_app = Gtk.Button(
            label=_("Close PyCUPS"),
            css_classes=["destructive-action"],
        )
        close_app.connect("clicked", lambda _button: self._on_quit())
        self.actions.append(close_app)
        content.append(self.actions)

        clamp.set_child(content)
        toolbar.set_content(clamp)
        self.set_content(toolbar)
        self.show_waiting()

    def show_waiting(self) -> None:
        self.visual.set_visible_child_name("waiting")
        self.spinner.start()
        self.heading.set_label(_("Restarting CUPS…"))
        self.description.set_label(
            _(
                "Waiting for the local print service to become available again. "
                "PyCUPS will continue automatically after the connection is confirmed."
            )
        )
        self.detail.set_visible(False)
        self.actions.set_visible(False)

    def show_failure(self, error: BaseException) -> None:
        self.spinner.stop()
        self.visual.set_visible_child_name("failure")
        self.heading.set_label(_("CUPS is still unavailable"))
        self.description.set_label(
            _(
                "PyCUPS remains blocked to avoid showing a false print-history error. "
                "It will try again automatically; you can also retry now or close the application."
            )
        )
        self.detail.set_label(str(error))
        self.detail.set_visible(True)
        self.actions.set_visible(True)

    def close_when_ready(self) -> None:
        self._closing_allowed = True
        self.set_deletable(True)
        self.close()

    def _retry(self) -> None:
        self.show_waiting()
        self._on_retry()

    def _close_requested(self, _window: Gtk.Window) -> bool:
        return not self._closing_allowed
