from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from print_archive.core.documents import (
    combine_pdfs,
    extract_pdf_pages,
    normalize_retrieved_document,
    prepare_documents,
)
from print_archive.core.page_ranges import parse_page_range
from print_archive.core.temp_store import PrivateTempStore
from print_archive.models import PrintJob, RetrievedDocument


def make_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for index in range(pages):
        writer.add_blank_page(width=200 + index, height=300 + index)
    with path.open("wb") as output:
        writer.write(output)


def sample_job(document_count: int = 1) -> PrintJob:
    return PrintJob(
        42,
        "Ten pages",
        "alice",
        "Office",
        "ipp://localhost/printers/Office",
        9,
        None,
        None,
        10,
        10,
        50,
        document_count,
        True,
        "application/pdf",
        {},
    )


class DocumentTests(unittest.TestCase):
    def test_extracts_only_selected_pdf_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ten.pdf"
            destination = root / "selected.pdf"
            make_pdf(source, 10)
            selection = parse_page_range("1,4,7-10", 10)

            extract_pdf_pages(source, selection, destination)

            result = PdfReader(str(destination))
            self.assertEqual(len(result.pages), 6)
            widths = [float(page.mediabox.width) for page in result.pages]
            self.assertEqual(widths, [200.0, 203.0, 206.0, 207.0, 208.0, 209.0])

    def test_combines_multi_document_pdf_job(self) -> None:
        with PrivateTempStore(prefix="print-archive-test-") as store:
            first = store.path("one.pdf")
            second = store.path("two.pdf")
            make_pdf(first, 2)
            make_pdf(second, 3)
            docs = (
                RetrievedDocument(1, "one.pdf", "application/pdf", first, 2),
                RetrievedDocument(2, "two.pdf", "application/pdf", second, 3),
            )

            prepared = prepare_documents(sample_job(2), docs, store)

            self.assertEqual(prepared.preview_kind, "pdf")
            self.assertEqual(prepared.total_pages, 5)
            self.assertTrue(prepared.supports_page_selection)
            self.assertEqual(len(PdfReader(str(prepared.printable_path)).pages), 5)

    def test_cached_jobs_keep_separate_spool_copies(self) -> None:
        with PrivateTempStore(prefix="print-archive-test-") as store:
            first_source = store.path("incoming-two-pages.pdf")
            make_pdf(first_source, 2)
            first = normalize_retrieved_document(
                {
                    "file": str(first_source),
                    "document-name": "report.pdf",
                    "document-format": "application/pdf",
                },
                1,
                store,
                job_id=41,
            )
            first_prepared = prepare_documents(sample_job(), (first,), store)

            second_source = store.path("incoming-one-page.pdf")
            make_pdf(second_source, 1)
            second = normalize_retrieved_document(
                {
                    "file": str(second_source),
                    "document-name": "invoice.pdf",
                    "document-format": "application/pdf",
                },
                1,
                store,
                job_id=42,
            )

            self.assertNotEqual(first.path, second.path)
            self.assertEqual(first.path.name, "job-41-document-1.pdf")
            self.assertEqual(second.path.name, "job-42-document-1.pdf")
            self.assertEqual(len(PdfReader(str(first_prepared.printable_path)).pages), 2)


if __name__ == "__main__":
    unittest.main()
