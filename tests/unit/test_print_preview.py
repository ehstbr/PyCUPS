from __future__ import annotations

import unittest

from pypdf import PdfReader, PdfWriter

from print_archive.core.print_preview import POINTS_PER_MM, compose_reprint_preview
from print_archive.core.temp_store import PrivateTempStore
from print_archive.models import MediaOption


class PrintPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PrivateTempStore(prefix="print-preview-test-")
        self.source = self.store.path("source.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=100)
        with self.source.open("wb") as output:
            writer.write(output)

    def tearDown(self) -> None:
        self.store.cleanup()

    def test_composes_the_source_on_the_selected_target_sheet(self) -> None:
        media = MediaOption(
            "iso_a4_210x297mm",
            "A4",
            210,
            297,
            margin_top_mm=4,
            margin_right_mm=3,
            margin_bottom_mm=4,
            margin_left_mm=3,
        )
        preview = compose_reprint_preview(self.source, 1, media, "fit", self.store)
        page = PdfReader(str(preview)).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 210 * POINTS_PER_MM, places=3)
        self.assertAlmostEqual(float(page.mediabox.height), 297 * POINTS_PER_MM, places=3)
        self.assertEqual(preview.stat().st_mode & 0o777, 0o600)

    def test_unknown_media_preserves_the_source_page_size(self) -> None:
        preview = compose_reprint_preview(self.source, 1, None, "none", self.store)
        page = PdfReader(str(preview)).pages[0]
        self.assertEqual(float(page.mediabox.width), 200.0)
        self.assertEqual(float(page.mediabox.height), 100.0)


if __name__ == "__main__":
    unittest.main()
