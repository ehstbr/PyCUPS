from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter

from ..models import PreparedJob, PrintJob, RetrievedDocument
from ..util.i18n import _
from .page_ranges import PageSelection
from .temp_store import PrivateTempStore


MIME_SUFFIXES = {
    "application/pdf": ".pdf",
    "application/postscript": ".ps",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
    "text/plain": ".txt",
}


def detect_mime(path: Path, declared: str | None = None) -> str:
    if declared and declared not in {"application/octet-stream", "application/vnd.cups-raw"}:
        return declared
    header = path.read_bytes()[:16]
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    guessed, _encoding = mimetypes.guess_type(path.name)
    return guessed or declared or "application/octet-stream"


def page_count(path: Path, mime_type: str) -> int | None:
    if mime_type != "application/pdf":
        return 1 if mime_type.startswith("image/") else None
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def normalize_retrieved_document(
    response: dict[str, object],
    number: int,
    store: PrivateTempStore,
    *,
    job_id: int,
) -> RetrievedDocument:
    source = Path(str(response["file"]))
    declared = str(response.get("document-format") or "application/octet-stream")
    name = Path(str(response.get("document-name") or f"document-{number}")).name
    mime_type = detect_mime(source, declared)
    suffix = Path(name).suffix or MIME_SUFFIXES.get(mime_type, ".bin")
    # Cached PreparedJob objects retain this path for the lifetime of the app.
    # Namespace spool copies by job so opening another job cannot overwrite a
    # previously cached multi-page PDF with a different document-1.pdf.
    target = store.path(f"job-{job_id}-document-{number}{suffix}")
    shutil.move(str(source), target)
    target.chmod(0o600)
    return RetrievedDocument(number, name, mime_type, target, page_count(target, mime_type))


def prepare_documents(
    job: PrintJob,
    documents: Iterable[RetrievedDocument],
    store: PrivateTempStore,
) -> PreparedJob:
    docs = tuple(documents)
    if not docs:
        return PreparedJob(job, docs, None, None, "unavailable")

    if all(doc.is_pdf for doc in docs):
        if len(docs) == 1:
            pdf_path = docs[0].path
        else:
            pdf_path = store.path(f"job-{job.job_id}-combined.pdf")
            combine_pdfs((doc.path for doc in docs), pdf_path)
        return PreparedJob(job, docs, pdf_path, page_count(pdf_path, "application/pdf"), "pdf")

    if len(docs) == 1:
        doc = docs[0]
        if doc.mime_type.startswith("image/"):
            return PreparedJob(job, docs, doc.path, doc.page_count, "image")
        if doc.mime_type.startswith("text/"):
            return PreparedJob(job, docs, doc.path, None, "text")
        return PreparedJob(job, docs, doc.path, None, "raw")

    return PreparedJob(job, docs, None, None, "mixed")


def combine_pdfs(paths: Iterable[Path], destination: Path) -> Path:
    writer = PdfWriter()
    for path in paths:
        reader = PdfReader(str(path))
        for pdf_page in reader.pages:
            writer.add_page(pdf_page)
    with destination.open("wb") as output:
        writer.write(output)
    destination.chmod(0o600)
    return destination


def extract_pdf_pages(source: Path, selection: PageSelection, destination: Path) -> Path:
    reader = PdfReader(str(source))
    if len(reader.pages) != selection.total_pages:
        raise ValueError(_("The PDF changed while its pages were being prepared."))
    writer = PdfWriter()
    for page_number in selection.pages:
        writer.add_page(reader.pages[page_number - 1])
    with destination.open("wb") as output:
        writer.write(output)
    destination.chmod(0o600)
    return destination
