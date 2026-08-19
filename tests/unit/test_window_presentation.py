from __future__ import annotations

import unittest

from print_archive.core.window_presentation import MappedWindowPresenter


class FakeWindow:
    def __init__(self, mapped: bool = False) -> None:
        self.mapped = mapped
        self.callback = None
        self.disconnected: list[int] = []

    def get_mapped(self) -> bool:
        return self.mapped

    def connect(self, _signal: str, callback: object) -> int:
        self.callback = callback
        return 7

    def disconnect(self, handler: int) -> None:
        self.disconnected.append(handler)


class MappedWindowPresenterTests(unittest.TestCase):
    def test_waits_until_parent_is_mapped(self) -> None:
        idle: list[object] = []
        shown: list[tuple[object, object]] = []
        parent = FakeWindow(mapped=False)
        presenter = MappedWindowPresenter(
            idle_add=lambda callback: idle.append(callback),
            show=lambda manifest, window: shown.append((manifest, window)),
            source_remove=False,
        )
        presenter.queue("release", parent)
        self.assertFalse(idle)
        parent.mapped = True
        parent.callback(parent)
        idle.pop()()
        self.assertEqual(shown, [("release", parent)])
        self.assertEqual(parent.disconnected, [7])

    def test_mapped_parent_is_deferred_to_idle(self) -> None:
        idle: list[object] = []
        shown: list[tuple[object, object]] = []
        parent = FakeWindow(mapped=True)
        presenter = MappedWindowPresenter(
            idle_add=lambda callback: idle.append(callback),
            show=lambda manifest, window: shown.append((manifest, window)),
            source_remove=False,
        )
        presenter.queue("release", parent)
        self.assertEqual(len(idle), 1)
        idle.pop()()
        self.assertEqual(shown, [("release", parent)])


if __name__ == "__main__":
    unittest.main()
