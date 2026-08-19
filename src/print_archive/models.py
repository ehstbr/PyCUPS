from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


JOB_STATE_LABELS = {
    3: "Waiting",
    4: "Held",
    5: "Printing",
    6: "Stopped",
    7: "Canceled",
    8: "Aborted",
    9: "Completed",
}


@dataclass(frozen=True, slots=True)
class PrintJob:
    job_id: int
    title: str
    user: str
    printer: str
    printer_uri: str
    state: int
    created_at: datetime | None
    completed_at: datetime | None
    pages: int | None
    pages_completed: int | None
    size_kib: int | None
    document_count: int
    preserved: bool | None
    document_format: str | None
    attributes: Mapping[str, Any] = field(repr=False, compare=False)

    @property
    def state_label(self) -> str:
        return JOB_STATE_LABELS.get(self.state, f"State {self.state}")

    @property
    def date(self) -> datetime | None:
        return self.completed_at or self.created_at

    @property
    def can_restart(self) -> bool:
        # job-preserved is only a hint. Ask CUPS directly: a retained document
        # may still be retrievable/restartable even when this attribute is false.
        return self.state in {7, 8, 9}


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    number: int
    name: str
    mime_type: str
    path: Path
    page_count: int | None

    @property
    def is_pdf(self) -> bool:
        return self.mime_type == "application/pdf" or self.path.suffix.lower() == ".pdf"


@dataclass(frozen=True, slots=True)
class PreparedJob:
    job: PrintJob
    documents: tuple[RetrievedDocument, ...]
    printable_path: Path | None
    total_pages: int | None
    preview_kind: str

    @property
    def supports_page_selection(self) -> bool:
        return self.printable_path is not None and self.preview_kind == "pdf" and bool(self.total_pages)


@dataclass(frozen=True, slots=True)
class ReprintResult:
    job_id: int
    restarted_original: bool
    page_description: str


@dataclass(frozen=True, slots=True)
class MediaOption:
    """One target-sheet size advertised by a CUPS destination."""

    keyword: str
    display_name: str
    width_mm: float | None = None
    height_mm: float | None = None
    margin_top_mm: float = 0.0
    margin_right_mm: float = 0.0
    margin_bottom_mm: float = 0.0
    margin_left_mm: float = 0.0

    @property
    def dimensions_text(self) -> str:
        if not self.width_mm or not self.height_mm:
            return ""
        return f"{self.width_mm:g} × {self.height_mm:g} mm"


@dataclass(frozen=True, slots=True)
class PrinterCapabilities:
    printer: str
    make_model: str
    media_options: tuple[MediaOption, ...]
    default_media_keyword: str | None
    scaling_supported: tuple[str, ...]
    default_scaling: str

    @property
    def default_media(self) -> MediaOption | None:
        if self.default_media_keyword:
            for media in self.media_options:
                if media.keyword == self.default_media_keyword:
                    return media
        return self.media_options[0] if self.media_options else None


@dataclass(frozen=True, slots=True)
class CupsServerSettings:
    web_interface: bool
    debug_logging: bool
    remote_admin: bool
    remote_any: bool
    share_printers: bool
    user_cancel_any: bool


@dataclass(frozen=True, slots=True)
class CupsSystemInfo:
    server: str
    user: str
    version: str
    default_printer: str | None
    printers: int


@dataclass(frozen=True, slots=True)
class RetentionSettings:
    preserve_files: str
    preserve_history: str
    max_jobs: int

    @property
    def files_days(self) -> int | None:
        return duration_days(self.preserve_files)

    @property
    def files_unlimited(self) -> bool:
        return self.preserve_files.strip().lower() in {"yes", "true", "on"}

    @property
    def history_days(self) -> int | None:
        return duration_days(self.preserve_history)

    @property
    def history_unlimited(self) -> bool:
        return self.preserve_history.strip().lower() in {"yes", "true", "on"}

    @property
    def max_jobs_unlimited(self) -> bool:
        return self.max_jobs == 0


def duration_days(value: str) -> int | None:
    normalized = str(value).strip().lower()
    if normalized in {"yes", "true", "on", "no", "false", "off", ""}:
        return None
    try:
        seconds = int(normalized)
    except ValueError:
        if normalized.endswith("d"):
            try:
                return max(0, int(normalized[:-1]))
            except ValueError:
                return None
        return None
    return max(0, round(seconds / 86_400))
