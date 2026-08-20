from __future__ import annotations

import unittest

from print_archive.core.preview_view import (
    MAX_ZOOM_PERCENT,
    MIN_ZOOM_PERCENT,
    clamp_zoom,
    fit_zoom_percent,
    normalize_rotation,
    rotated_dimensions,
    stepped_zoom,
    zoomed_dimensions,
)


class PreviewViewTests(unittest.TestCase):
    def test_rotation_is_normalized_and_swaps_dimensions(self) -> None:
        self.assertEqual(normalize_rotation(-90), 270)
        self.assertEqual(normalize_rotation(450), 90)
        self.assertEqual(rotated_dimensions(1200, 800, 0), (1200, 800))
        self.assertEqual(rotated_dimensions(1200, 800, 90), (800, 1200))
        self.assertEqual(rotated_dimensions(1200, 800, 270), (800, 1200))

    def test_zoom_is_bounded_and_uses_predictable_steps(self) -> None:
        self.assertEqual(clamp_zoom(1), MIN_ZOOM_PERCENT)
        self.assertEqual(clamp_zoom(900), MAX_ZOOM_PERCENT)
        self.assertEqual(stepped_zoom(100, 1), 110)
        self.assertEqual(stepped_zoom(100, -2), 80)

    def test_fit_zoom_uses_both_viewport_dimensions(self) -> None:
        self.assertEqual(
            fit_zoom_percent(1000, 500, 524, 524, padding=24),
            50.0,
        )
        self.assertEqual(
            fit_zoom_percent(500, 1000, 524, 524, padding=24),
            50.0,
        )
        self.assertEqual(fit_zoom_percent(0, 1000, 524, 524), 100.0)

    def test_zoomed_dimensions_never_collapse(self) -> None:
        self.assertEqual(zoomed_dimensions(1000, 500, 50), (500, 250))
        self.assertEqual(zoomed_dimensions(1, 1, 10), (1, 1))


if __name__ == "__main__":
    unittest.main()
