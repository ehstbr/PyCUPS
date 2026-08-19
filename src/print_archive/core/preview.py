from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..util.i18n import _
from .temp_store import PrivateTempStore


class PreviewError(RuntimeError):
    pass


def render_pdf_page(
    pdf_path: Path,
    page_number: int,
    store: PrivateTempStore,
    *,
    width: int = 1100,
) -> Path:
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise PreviewError(_("Install poppler-utils to preview PDF files."))
    output_prefix = store.path(f"preview-{pdf_path.stem}-{page_number}")
    command = [
        renderer,
        "-f",
        str(page_number),
        "-l",
        str(page_number),
        "-singlefile",
        "-scale-to-x",
        str(width),
        "-scale-to-y",
        "-1",
        "-png",
        str(pdf_path),
        str(output_prefix),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or _("Unknown PDF rendering error.")
        raise PreviewError(detail)
    result = output_prefix.with_suffix(".png")
    if not result.is_file():
        raise PreviewError(_("The PDF renderer did not create a preview."))
    result.chmod(0o600)
    return result
