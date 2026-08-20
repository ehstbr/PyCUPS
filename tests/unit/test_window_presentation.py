from __future__ import annotations

import unittest

from print_archive.core.window_presentation import MappedWindowPresenter


class FakeWindow:
    def __init__(self, mapped: bool = False, active: bool = False) -> None:
        self.mapped = mapped
        self.active = active
        self.callbacks: dict[str, object] = {}
        self.disconnected: list[int] = []

    def get_mapped(self) -> bool:
        return self.mapped

    def is_active(self) -> bool:
        return self.active

    def connect(self, signal: str, callback: object) -> int:
        self.callbacks[signal] = callback
        return len(self.callbacks)

    def disconnect(self, handler: int) -> None:
        self.disconnected.append(handler)

    def emit(self, signal: str) -> None:
        callback = self.callbacks[signal]
        callback(self, None) if signal.startswith("notify::") else callback(self)


class MappedWindowPresenterTests(unittest.TestCase):
    def test_waits_until_parent_is_mapped_and_active(self) -> None:
        idle: list[object] = []
        shown: list[tuple[object, object]] = []
        parent = FakeWindow(mapped=False, active=False)
        presenter = MappedWindowPresenter(
            idle_add=lambda callback: idle.append(callback),
            show=lambda manifest, window: shown.append((manifest, window)),
            source_remove=False,
        )
        presenter.queue("release", parent)
        self.assertFalse(idle)
        parent.mapped = True
        parent.emit("map")
        self.assertFalse(idle)
        parent.active = True
        parent.emit("notify::is-active")
        idle.pop()()
        self.assertEqual(shown, [("release", parent)])
        self.assertEqual(parent.disconnected, [1, 2])

    def test_mapped_parent_waits_until_it_becomes_active(self) -> None:
        idle: list[object] = []
        shown: list[tuple[object, object]] = []
        parent = FakeWindow(mapped=True, active=False)
        presenter = MappedWindowPresenter(
            idle_add=lambda callback: idle.append(callback),
            show=lambda manifest, window: shown.append((manifest, window)),
            source_remove=False,
        )
        presenter.queue("release", parent)
        self.assertFalse(idle)
        parent.active = True
        parent.emit("notify::is-active")
        idle.pop()()
        self.assertEqual(shown, [("release", parent)])

    def test_ready_parent_is_deferred_to_idle(self) -> None:
        idle: list[object] = []
        shown: list[tuple[object, object]] = []
        parent = FakeWindow(mapped=True, active=True)
        presenter = MappedWindowPresenter(
            idle_add=lambda callback: idle.append(callback),
            show=lambda manifest, window: shown.append((manifest, window)),
            source_remove=False,
        )
        presenter.queue("release", parent)
        self.assertEqual(len(idle), 1)
        idle.pop()()
        self.assertEqual(shown, [("release", parent)])

    def test_replaced_request_ignores_stale_idle_callback(self) -> None:
        idle: list[object] = []
        shown: list[tuple[object, object]] = []
        first_parent = FakeWindow(mapped=True, active=True)
        second_parent = FakeWindow(mapped=True, active=True)
        presenter = MappedWindowPresenter(
            idle_add=lambda callback: idle.append(callback),
            show=lambda manifest, window: shown.append((manifest, window)),
            source_remove=False,
        )
        presenter.queue("first", first_parent)
        first_parent.emit("notify::is-active")
        self.assertEqual(len(idle), 1)
        stale_callback = idle.pop()

        presenter.queue("second", second_parent)
        self.assertEqual(len(idle), 1)
        stale_callback()
        self.assertFalse(shown)
        idle.pop()()
        self.assertEqual(shown, [("second", second_parent)])


if __name__ == "__main__":
    unittest.main()
