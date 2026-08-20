from __future__ import annotations

from collections.abc import Callable
from typing import Any


class MappedWindowPresenter:
    """Present a child only after its intended parent is mapped and active."""

    def __init__(
        self,
        *,
        idle_add: Callable[[Callable[[], Any]], Any],
        show: Callable[[Any, Any], None],
        source_remove: Any,
    ) -> None:
        self._idle_add = idle_add
        self._show = show
        self._source_remove = source_remove
        self._manifest: Any = None
        self._parent: Any = None
        self._parent_handlers: list[int] = []
        self._present_scheduled = False
        self._generation = 0

    def queue(self, manifest: Any, parent: Any) -> None:
        self.clear()
        self._manifest = manifest
        self._parent = parent
        self._parent_handlers = [
            parent.connect("map", self._parent_state_changed),
            parent.connect("notify::is-active", self._parent_state_changed),
        ]
        self._schedule_if_ready()

    def clear(self) -> None:
        self._generation += 1
        if self._parent is not None:
            for handler in self._parent_handlers:
                try:
                    self._parent.disconnect(handler)
                except (TypeError, RuntimeError):
                    pass
        self._manifest = None
        self._parent = None
        self._parent_handlers = []
        self._present_scheduled = False

    def _parent_state_changed(self, *_args: Any) -> None:
        self._schedule_if_ready()

    def _schedule_if_ready(self) -> None:
        parent = self._parent
        # GtkWidget::map is emitted before the compositor necessarily finishes
        # activating and placing a new toplevel. Presenting its transient child
        # in that gap can center the child against incomplete startup geometry.
        if (
            parent is None
            or self._present_scheduled
            or not parent.get_mapped()
            or not parent.is_active()
        ):
            return
        self._present_scheduled = True
        generation = self._generation
        self._idle_add(lambda: self._present(generation))

    def _present(self, generation: int) -> Any:
        if generation != self._generation:
            return self._source_remove
        self._present_scheduled = False
        manifest = self._manifest
        parent = self._parent
        if manifest is None or parent is None:
            self.clear()
            return self._source_remove
        if not parent.get_mapped() or not parent.is_active():
            return self._source_remove
        self.clear()
        self._show(manifest, parent)
        return self._source_remove
