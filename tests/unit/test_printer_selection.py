from __future__ import annotations

import unittest

from print_archive.core.printer_selection import PrinterSelection


class PrinterSelectionTests(unittest.TestCase):
    def test_starts_with_all_printers_selected(self) -> None:
        selection = PrinterSelection.all(["Thermal", "Laser", "Laser"])
        self.assertEqual(selection.available, ("Laser", "Thermal"))
        self.assertTrue(selection.all_selected)
        self.assertTrue(selection.matches("Laser"))

    def test_supports_any_subset_and_an_empty_intermediate_state(self) -> None:
        selection = PrinterSelection.all(["Laser", "PDF", "Thermal"])
        selection = selection.set_selected("PDF", False)
        selection = selection.set_selected("Thermal", False)
        self.assertEqual(selection.selected, frozenset({"Laser"}))
        self.assertFalse(selection.all_selected)
        self.assertFalse(selection.matches("PDF"))
        self.assertEqual(selection.select_all(False).count, 0)

    def test_refresh_preserves_a_subset_but_expands_all_mode(self) -> None:
        subset = PrinterSelection.all(["Laser", "PDF"]).set_selected("PDF", False)
        self.assertEqual(
            subset.with_available(["Laser", "PDF", "Thermal"]).selected,
            frozenset({"Laser"}),
        )
        expanded = PrinterSelection.all(["Laser", "PDF"]).with_available(
            ["Laser", "PDF", "Thermal"]
        )
        self.assertTrue(expanded.all_selected)


if __name__ == "__main__":
    unittest.main()
