from __future__ import annotations

import unittest

from print_archive.core.printer_capabilities import (
    media_from_keyword,
    parse_printer_capabilities,
)


class PrinterCapabilitiesTests(unittest.TestCase):
    def test_parses_media_collections_margins_and_defaults(self) -> None:
        capabilities = parse_printer_capabilities(
            "Office",
            {
                "printer-make-and-model": "Example 2000",
                "media-col-database": [
                    {
                        "media-key": "iso_a4_210x297mm",
                        "media-size": {"x-dimension": 21000, "y-dimension": 29700},
                        "media-top-margin": 400,
                        "media-right-margin": 300,
                        "media-bottom-margin": 400,
                        "media-left-margin": 300,
                    }
                ],
                "media-default": "iso_a4_210x297mm",
                "media-supported": ["iso_a4_210x297mm", "na_letter_8.5x11in"],
                "print-scaling-supported": ["none", "fill", "fit"],
                "print-scaling-default": "none",
            },
        )
        self.assertEqual(capabilities.make_model, "Example 2000")
        self.assertEqual(capabilities.default_media.display_name, "A4")
        self.assertEqual(capabilities.default_media.width_mm, 210.0)
        self.assertEqual(capabilities.default_media.margin_top_mm, 4.0)
        self.assertEqual(capabilities.scaling_supported, ("fit", "fill", "none"))
        self.assertEqual(capabilities.default_scaling, "none")

    def test_understands_metric_and_inch_media_keywords(self) -> None:
        a4 = media_from_keyword("iso_a4_210x297mm")
        letter = media_from_keyword("na_letter_8.5x11in")
        self.assertEqual((a4.width_mm, a4.height_mm), (210.0, 297.0))
        self.assertEqual((letter.width_mm, letter.height_mm), (215.9, 279.4))

    def test_has_bounded_scaling_fallback_when_ipp_omits_it(self) -> None:
        capabilities = parse_printer_capabilities("Legacy", {})
        self.assertEqual(capabilities.scaling_supported, ("fit", "fill", "none"))
        self.assertEqual(capabilities.default_scaling, "fit")


if __name__ == "__main__":
    unittest.main()
