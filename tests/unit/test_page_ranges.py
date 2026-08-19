from __future__ import annotations

import unittest

from print_archive.core.page_ranges import (
    PageRangeError,
    all_pages,
    compact_page_range,
    parse_page_range,
)


class PageRangeTests(unittest.TestCase):
    def test_single_page(self) -> None:
        selection = parse_page_range("4", 10)
        self.assertEqual(selection.pages, (4,))
        self.assertEqual(selection.label, "4")
        self.assertFalse(selection.is_all)

    def test_mixed_ranges_are_sorted_and_deduplicated(self) -> None:
        selection = parse_page_range("7-10, 1, 4, 8", 10)
        self.assertEqual(selection.pages, (1, 4, 7, 8, 9, 10))
        self.assertEqual(selection.label, "1,4,7-10")

    def test_all_pages(self) -> None:
        selection = all_pages(3)
        self.assertTrue(selection.is_all)
        self.assertEqual(selection.label, "all pages")

    def test_compaction(self) -> None:
        self.assertEqual(compact_page_range([1, 2, 3, 5, 8, 9]), "1-3,5,8-9")

    def test_invalid_values(self) -> None:
        cases = ("", "0", "11", "5-2", "1,,3", "a", "1-2-3")
        for expression in cases:
            with self.subTest(expression=expression):
                with self.assertRaises(PageRangeError):
                    parse_page_range(expression, 10)


if __name__ == "__main__":
    unittest.main()

