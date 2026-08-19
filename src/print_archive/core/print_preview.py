from __future__ import annotations

import re
import uuid
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

from ..models import MediaOption
from .temp_store import PrivateTempStore


POINTS_PER_MM = 72.0 / 25.4


def compose_reprint_preview(
    source_pdf: Path,
    page_number: int,
    media: MediaOption | None,
    scaling: str,
    store: PrivateTempStore,
) -> Path:
    """Create a one-page PDF approximating the chosen CUPS target sheet."""

    reader = PdfReader(str(source_pdf))
    if page_number < 1 or page_number > len(reader.pages):
        raise ValueError("Preview page is outside the PDF page range.")
    source_page = reader.pages[page_number - 1]
    transfer_rotation = getattr(source_page, "transfer_rotation_to_content", None)
    if callable(transfer_rotation):
        transfer_rotation()

    source_width = float(source_page.mediabox.width)
    source_height = float(source_page.mediabox.height)
    if source_width <= 0 or source_height <= 0:
        raise ValueError("The source PDF page has invalid dimensions.")

    if media and media.width_mm and media.height_mm:
        target_width = media.width_mm * POINTS_PER_MM
        target_height = media.height_mm * POINTS_PER_MM
        left = max(0.0, media.margin_left_mm * POINTS_PER_MM)
        right = max(0.0, media.margin_right_mm * POINTS_PER_MM)
        bottom = max(0.0, media.margin_bottom_mm * POINTS_PER_MM)
        top = max(0.0, media.margin_top_mm * POINTS_PER_MM)
    else:
        target_width = source_width
        target_height = source_height
        left = right = bottom = top = 0.0

    printable_width = max(1.0, target_width - left - right)
    printable_height = max(1.0, target_height - bottom - top)
    if scaling == "none":
        factor = 1.0
    elif scaling == "fill":
        factor = max(printable_width / source_width, printable_height / source_height)
    elif scaling == "auto":
        factor = min(
            1.0,
            printable_width / source_width,
            printable_height / source_height,
        )
    else:
        factor = min(printable_width / source_width, printable_height / source_height)

    x = left + (printable_width - source_width * factor) / 2.0
    y = bottom + (printable_height - source_height * factor) / 2.0
    writer = PdfWriter()
    target_page = writer.add_blank_page(width=target_width, height=target_height)
    target_page.merge_transformed_page(
        source_page,
        Transformation().scale(factor).translate(x, y),
        over=True,
    )

    media_key = _safe_component(media.keyword if media else "source")
    destination = store.path(
        f"reprint-preview-{source_pdf.stem}-{page_number}-{media_key}-{scaling}-"
        f"{uuid.uuid4().hex}.pdf"
    )
    with destination.open("wb") as output:
        writer.write(output)
    destination.chmod(0o600)
    return destination


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "unknown"
