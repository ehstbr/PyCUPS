from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar
from urllib.parse import quote

from ..models import (
    CupsServerSettings,
    CupsSystemInfo,
    MediaOption,
    PreparedJob,
    PrintJob,
    PrinterCapabilities,
    ReprintResult,
    RetentionSettings,
    RetrievedDocument,
)
from ..util.i18n import _
from .documents import extract_pdf_pages, normalize_retrieved_document, prepare_documents
from .page_ranges import PageSelection, all_pages
from .preview import render_pdf_page
from .print_preview import compose_reprint_preview
from .printer_capabilities import parse_printer_capabilities
from .temp_store import PrivateTempStore


class CupsServiceError(RuntimeError):
    pass


class DocumentUnavailableError(CupsServiceError):
    pass


class AuthenticationCanceledError(CupsServiceError):
    pass


class SettingsError(CupsServiceError):
    pass


class CupsRestartError(CupsServiceError):
    pass


T = TypeVar("T")
AuthProvider = Callable[[str, str, str, str], tuple[str, str] | None]


class CupsService:
    """Thin, testable façade over PyCUPS and the system cupsctl helper."""

    REQUESTED_JOB_ATTRIBUTES = [
        "job-id",
        "job-name",
        "job-originating-user-name",
        "job-printer-uri",
        "job-state",
        "job-preserved",
        "job-k-octets",
        "job-media-sheets",
        "job-media-sheets-completed",
        "number-of-documents",
        "document-format",
        "time-at-creation",
        "time-at-completed",
    ]
    REQUESTED_PRINTER_ATTRIBUTES = [
        "printer-make-and-model",
        "media-col-database",
        "media-col-default",
        "media-col-ready",
        "media-supported",
        "media-default",
        "media-ready",
        "print-scaling-supported",
        "print-scaling-default",
    ]

    def __init__(
        self,
        *,
        cups_module: Any | None = None,
        connection: Any | None = None,
        store: PrivateTempStore | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        if cups_module is None:
            try:
                import cups as cups_module  # type: ignore[no-redef]
            except ImportError as error:
                raise CupsServiceError(_("python3-cups is required to access the print service.")) from error
        self.cups = cups_module
        self.connection = connection or cups_module.Connection()
        self.store = store or PrivateTempStore()
        self._run = command_runner
        self._auth_provider: AuthProvider | None = None
        # A PyCUPS Connection is shared by the background tasks. Keep IPP
        # operations serialized while allowing PDF rendering to stay parallel.
        self._connection_lock = threading.RLock()

    def set_auth_provider(self, provider: AuthProvider | None) -> None:
        """Set the UI callback used only when CUPS challenges an operation."""
        self._auth_provider = provider

    def close(self) -> None:
        self.store.cleanup()

    def list_jobs(self, limit: int = 500) -> list[PrintJob]:
        raw_jobs: dict[int, Mapping[str, Any]] = {}
        with self._connection_lock:
            for which in ("completed", "not-completed"):
                try:
                    result = self.connection.getJobs(
                        which_jobs=which,
                        my_jobs=False,
                        limit=limit,
                        requested_attributes=self.REQUESTED_JOB_ATTRIBUTES,
                    )
                except TypeError:
                    result = self.connection.getJobs(which_jobs=which, my_jobs=False, limit=limit)
                raw_jobs.update({int(job_id): attributes for job_id, attributes in result.items()})
        jobs = [self._to_job(job_id, attrs) for job_id, attrs in raw_jobs.items()]
        jobs.sort(key=lambda item: item.date or datetime.min, reverse=True)
        return jobs

    def get_job(self, job_id: int) -> PrintJob:
        with self._connection_lock:
            try:
                attrs = self.connection.getJobAttributes(
                    job_id, requested_attributes=self.REQUESTED_JOB_ATTRIBUTES
                )
            except TypeError:
                attrs = self.connection.getJobAttributes(job_id)
        return self._to_job(job_id, attrs)

    def list_printers(self) -> list[str]:
        with self._connection_lock:
            printers = self.connection.getPrinters()
        return sorted(printers, key=str.casefold)

    def get_printer_capabilities(self, printer: str) -> PrinterCapabilities:
        with self._connection_lock:
            try:
                attributes = self.connection.getPrinterAttributes(
                    name=printer,
                    requested_attributes=self.REQUESTED_PRINTER_ATTRIBUTES,
                )
            except TypeError:
                try:
                    attributes = self.connection.getPrinterAttributes(name=printer)
                except TypeError:
                    attributes = self.connection.getPrinterAttributes(printer)
        return parse_printer_capabilities(printer, attributes)

    def list_reprint_destinations(
        self,
    ) -> tuple[list[str], dict[str, PrinterCapabilities]]:
        printers = self.list_printers()
        capabilities: dict[str, PrinterCapabilities] = {}
        for printer in printers:
            try:
                capabilities[printer] = self.get_printer_capabilities(printer)
            except Exception:
                capabilities[printer] = parse_printer_capabilities(printer, {})
        return printers, capabilities

    def create_reprint_preview(
        self,
        prepared: PreparedJob,
        *,
        page_number: int,
        media: MediaOption | None,
        scaling: str,
    ) -> Path:
        if not prepared.printable_path or prepared.preview_kind != "pdf":
            raise DocumentUnavailableError(
                _("A target-sheet preview is available for retained PDF jobs only.")
            )
        preview_pdf = compose_reprint_preview(
            prepared.printable_path,
            page_number,
            media,
            scaling,
            self.store,
        )
        return render_pdf_page(preview_pdf, 1, self.store, width=900)

    def retrieve_job(self, job: PrintJob) -> PreparedJob:
        docs: list[RetrievedDocument] = []
        current_number = 1

        def retrieve() -> PreparedJob:
            nonlocal current_number
            for number in range(1, max(1, job.document_count) + 1):
                current_number = number
                response = self.connection.getDocument(job.printer_uri, job.job_id, number)
                docs.append(
                    normalize_retrieved_document(
                        response,
                        number,
                        self.store,
                        job_id=job.job_id,
                    )
                )
            return prepare_documents(job, docs, self.store)

        try:
            return self._run_authenticated(retrieve)
        except AuthenticationCanceledError:
            raise
        except Exception as error:
            if docs:
                raise DocumentUnavailableError(
                    _("Document {number} of this job could not be retrieved.").format(
                        number=current_number
                    )
                ) from error
            raise DocumentUnavailableError(_document_error_message(error)) from error

    def reprint(
        self,
        prepared: PreparedJob,
        *,
        printer: str,
        copies: int = 1,
        selection: PageSelection | None = None,
        preserve_original: bool = True,
        media_keyword: str | None = None,
        scaling: str | None = None,
    ) -> ReprintResult:
        if copies < 1 or copies > 999:
            raise CupsServiceError(_("Copies must be between 1 and 999."))

        if selection is None and prepared.total_pages:
            selection = all_pages(prepared.total_pages)

        exact_restart = (
            preserve_original
            and
            printer == prepared.job.printer
            and copies == 1
            and (selection is None or selection.is_all)
        )
        if exact_restart:
            try:
                self._run_authenticated(
                    lambda: self.connection.restartJob(prepared.job.job_id)
                )
            except AuthenticationCanceledError:
                raise
            except Exception as error:
                raise CupsServiceError(
                    _("CUPS could not restart job #{job_id}: {detail}").format(
                        job_id=prepared.job.job_id,
                        detail=_error_detail(error),
                    )
                ) from error
            return ReprintResult(prepared.job.job_id, True, _("all pages"))

        if prepared.preview_kind == "raw":
            raise CupsServiceError(
                _("Raw printer data can only be restarted exactly on its original printer.")
            )
        if prepared.printable_path is None:
            raise DocumentUnavailableError(
                _("This multi-document job can only be restarted exactly on its original printer.")
            )

        print_path = prepared.printable_path
        page_description = _("all pages")
        if selection is not None and not selection.is_all:
            if not prepared.supports_page_selection:
                raise CupsServiceError(_("Selected-page reprinting is available for PDF jobs only."))
            print_path = self.store.path(
                f"job-{prepared.job.job_id}-pages-{selection.label.replace(',', '_')}.pdf"
            )
            extract_pdf_pages(prepared.printable_path, selection, print_path)
            page_description = selection.label

        title = f"Reprint of {prepared.job.title}"
        options = {"copies": str(copies)}
        if media_keyword:
            if len(media_keyword) > 255 or not re.fullmatch(r"[A-Za-z0-9_.:+-]+", media_keyword):
                raise CupsServiceError(_("The selected paper size is invalid."))
            options["media"] = media_keyword
        if scaling:
            if scaling not in {"auto", "auto-fit", "fit", "fill", "none"}:
                raise CupsServiceError(_("The selected scaling mode is invalid."))
            options["print-scaling"] = scaling
        try:
            new_job_id = int(
                self._run_authenticated(
                    lambda: self.connection.printFile(
                        printer, str(print_path), title, options
                    )
                )
            )
        except AuthenticationCanceledError:
            raise
        except Exception as error:
            raise CupsServiceError(
                _("CUPS could not submit the reprint: {detail}").format(
                    detail=_error_detail(error)
                )
            ) from error
        return ReprintResult(new_job_id, False, page_description)

    def export_original(self, prepared: PreparedJob, destination: Path) -> Path:
        if prepared.printable_path is None:
            raise DocumentUnavailableError(_("This job cannot be exported as a single file."))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prepared.printable_path, destination)
        return destination

    def purge_job(self, job_id: int) -> None:
        try:
            self._run_authenticated(
                lambda: self.connection.cancelJob(job_id, purge_job=True)
            )
        except AuthenticationCanceledError:
            raise
        except Exception as error:
            raise CupsServiceError(
                _("CUPS could not delete job #{job_id}: {detail}").format(
                    job_id=job_id,
                    detail=_error_detail(error),
                )
            ) from error

    def purge_all_jobs(self) -> int:
        jobs = self.list_jobs(limit=100_000)
        failures: list[str] = []
        removed = 0
        for job in jobs:
            try:
                self.purge_job(job.job_id)
                removed += 1
            except Exception as error:
                failures.append(f"#{job.job_id}: {error}")
        if failures:
            sample = "; ".join(failures[:3])
            raise CupsServiceError(
                _("Removed {removed} jobs, but {failed} could not be removed: {sample}").format(
                    removed=removed, failed=len(failures), sample=sample
                )
            )
        return removed

    def read_retention_settings(self) -> RetentionSettings:
        values = self._read_cupsctl_values()
        return RetentionSettings(
            preserve_files=values.get("preservejobfiles", "86400"),
            preserve_history=values.get("preservejobhistory", "Yes"),
            max_jobs=_safe_int(values.get("maxjobs"), 500),
        )

    def apply_retention_settings(
        self,
        *,
        files_days: int | None,
        history_days: int | None,
        max_jobs: int | None,
        helper_path: Path | None = None,
    ) -> None:
        if files_days is not None and not 1 <= files_days <= 3650:
            raise SettingsError(_("File retention must be between 1 and 3650 days."))
        if history_days is not None and not 1 <= history_days <= 3650:
            raise SettingsError(_("History retention must be between 1 and 3650 days."))
        if max_jobs is not None and not 1 <= max_jobs <= 1_000_000:
            raise SettingsError(_("MaxJobs must be between 1 and 1,000,000, or unlimited."))

        helper = helper_path or Path("/usr/lib/print-archive/apply-settings")
        if not helper.is_file():
            raise SettingsError(_("The administrative settings helper is not installed."))
        command = [
            "pkexec",
            str(helper),
            "retention",
            "Yes" if files_days is None else str(files_days * 86_400),
            "Yes" if history_days is None else str(history_days * 86_400),
            "0" if max_jobs is None else str(max_jobs),
        ]
        completed = self._run(command, capture_output=True, text=True, timeout=90, check=False)
        if completed.returncode != 0:
            detail = completed.stderr.strip()
            if completed.returncode in {126, 127}:
                detail = _("Administrator authentication was canceled.")
            raise SettingsError(detail or _("CUPS rejected the new retention settings."))

    def read_server_settings(self) -> CupsServerSettings:
        values = self._read_cupsctl_values()
        return CupsServerSettings(
            web_interface=_setting_bool(values, "webinterface", True),
            debug_logging=_setting_bool(values, "_debug_logging", False),
            remote_admin=_setting_bool(values, "_remote_admin", False),
            remote_any=_setting_bool(values, "_remote_any", False),
            share_printers=_setting_bool(values, "_share_printers", False),
            user_cancel_any=_setting_bool(values, "_user_cancel_any", False),
        )

    def apply_server_settings(
        self,
        settings: CupsServerSettings,
        *,
        helper_path: Path | None = None,
    ) -> None:
        if not isinstance(settings, CupsServerSettings):
            raise SettingsError(_("Invalid global CUPS settings."))
        helper = helper_path or Path("/usr/lib/print-archive/apply-settings")
        if not helper.is_file():
            raise SettingsError(_("The administrative settings helper is not installed."))
        values = (
            settings.web_interface,
            settings.debug_logging,
            settings.remote_admin,
            settings.remote_any,
            settings.share_printers,
            settings.user_cancel_any,
        )
        command = [
            "pkexec",
            str(helper),
            "server",
            *("yes" if value else "no" for value in values),
        ]
        completed = self._run(command, capture_output=True, text=True, timeout=90, check=False)
        if completed.returncode != 0:
            detail = completed.stderr.strip()
            if completed.returncode in {126, 127}:
                detail = _("Administrator authentication was canceled.")
            raise SettingsError(detail or _("CUPS rejected the global server settings."))

    def wait_for_cups_ready(
        self,
        *,
        timeout: float = 30.0,
        interval: float = 0.4,
        initial_delay: float = 0.6,
        stable_checks: int = 3,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Poll fresh IPP connections until the restarted scheduler is stable."""

        if timeout < 0 or interval < 0 or initial_delay < 0 or stable_checks < 1:
            raise ValueError("Invalid CUPS readiness wait parameters.")

        deadline = time.monotonic() + timeout
        consecutive_ready = 0
        last_error: BaseException | None = None
        self._restart_wait_delay(initial_delay, cancel_event)

        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise CupsRestartError(_("The CUPS restart wait was canceled."))

            try:
                candidate = self.cups.Connection()
                candidate.getPrinters()
            except Exception as error:
                last_error = error
                consecutive_ready = 0
            else:
                consecutive_ready += 1
                if consecutive_ready >= stable_checks:
                    # Do not keep using the connection that existed before the
                    # scheduler reload. All subsequent jobs use this verified,
                    # newly-created IPP connection.
                    with self._connection_lock:
                        self.connection = candidate
                    return

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._restart_wait_delay(min(interval, remaining), cancel_event)

        message = _(
            "CUPS did not become available again after the configuration change."
        )
        if last_error is not None:
            message = _("{message} Last connection error: {detail}").format(
                message=message,
                detail=_error_detail(last_error),
            )
        raise CupsRestartError(message)

    @staticmethod
    def _restart_wait_delay(
        delay: float,
        cancel_event: threading.Event | None,
    ) -> None:
        if delay <= 0:
            return
        if cancel_event is not None:
            if cancel_event.wait(delay):
                raise CupsRestartError(_("The CUPS restart wait was canceled."))
            return
        time.sleep(delay)

    def read_system_info(self) -> CupsSystemInfo:
        get_server = getattr(self.cups, "getServer", None)
        get_user = getattr(self.cups, "getUser", None)
        server = str(get_server()) if callable(get_server) else "localhost"
        user = str(get_user()) if callable(get_user) else ""
        version = str(
            getattr(self.cups, "CUPS_VERSION", None)
            or getattr(self.cups, "__version__", None)
            or _("unknown")
        )
        with self._connection_lock:
            printers = self.connection.getPrinters()
            try:
                default_printer = self.connection.getDefault()
            except Exception:
                default_printer = None
        return CupsSystemInfo(
            server=server,
            user=user,
            version=version,
            default_printer=str(default_printer) if default_printer else None,
            printers=len(printers),
        )

    def _read_cupsctl_values(self) -> dict[str, str]:
        cupsctl = shutil.which("cupsctl")
        if cupsctl is None:
            raise SettingsError(_("cupsctl was not found. Install cups-client."))
        completed = self._run(
            [cupsctl], capture_output=True, text=True, timeout=15, check=False
        )
        if completed.returncode != 0:
            raise SettingsError(completed.stderr.strip() or _("Could not read CUPS settings."))
        values: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip().lower()] = value.strip()
        return values

    @staticmethod
    def cups_defaults() -> RetentionSettings:
        return RetentionSettings("86400", "Yes", 500)

    def _run_authenticated(self, operation: Callable[[], T]) -> T:
        """Run one IPP operation with a thread-local PyCUPS password callback."""
        with self._connection_lock:
            provider = self._auth_provider
            set_password_callback = getattr(self.cups, "setPasswordCB2", None)
            get_user = getattr(self.cups, "getUser", None)
            set_user = getattr(self.cups, "setUser", None)
            if provider is None or not callable(set_password_callback):
                return operation()

            original_user = str(get_user()) if callable(get_user) else ""
            authentication_canceled = False

            def password_callback(
                prompt: str,
                _connection: object,
                method: str,
                resource: str,
            ) -> str | None:
                nonlocal authentication_canceled
                current_user = str(get_user()) if callable(get_user) else original_user
                credentials = provider(
                    str(prompt), current_user, str(method), str(resource)
                )
                if credentials is None:
                    authentication_canceled = True
                    return None
                username, password = credentials
                if not username or not password:
                    authentication_canceled = True
                    return None
                if callable(set_user):
                    set_user(username)
                return password

            set_password_callback(password_callback)
            try:
                return operation()
            except Exception as error:
                if authentication_canceled:
                    raise AuthenticationCanceledError(
                        _("CUPS authentication was canceled.")
                    ) from error
                raise
            finally:
                # PyCUPS tracks both values per thread. Restore them before this
                # executor thread is reused and never retain the returned password.
                set_password_callback(None)
                if original_user and callable(set_user):
                    set_user(original_user)

    def _to_job(self, job_id: int, attrs: Mapping[str, Any]) -> PrintJob:
        printer_uri = str(attrs.get("job-printer-uri") or "")
        printer = _printer_name(printer_uri) or str(attrs.get("printer-name") or "Unknown")
        return PrintJob(
            job_id=int(attrs.get("job-id") or job_id),
            title=str(attrs.get("job-name") or f"Job {job_id}"),
            user=str(attrs.get("job-originating-user-name") or "Unknown"),
            printer=printer,
            printer_uri=printer_uri or f"ipp://localhost/printers/{quote(printer)}",
            state=_safe_int(attrs.get("job-state"), 0),
            created_at=_timestamp(attrs.get("time-at-creation")),
            completed_at=_timestamp(attrs.get("time-at-completed")),
            pages=_optional_int(attrs.get("job-media-sheets")),
            pages_completed=_optional_int(attrs.get("job-media-sheets-completed")),
            size_kib=_optional_int(attrs.get("job-k-octets")),
            document_count=max(1, _safe_int(attrs.get("number-of-documents"), 1)),
            preserved=_optional_bool(attrs.get("job-preserved")),
            document_format=_optional_str(attrs.get("document-format")),
            attributes=dict(attrs),
        )


def _printer_name(uri: str) -> str:
    match = re.search(r"/(?:printers|classes)/([^/?#]+)", uri)
    if not match:
        return ""
    from urllib.parse import unquote

    return unquote(match.group(1))


def _timestamp(value: object) -> datetime | None:
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds)
    except (OSError, OverflowError, ValueError):
        return None


def _safe_int(value: object, fallback: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return fallback


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _safe_int(value, 0)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"yes", "true", "on", "1"}
    return bool(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _setting_bool(values: Mapping[str, str], key: str, fallback: bool) -> bool:
    value = values.get(key.lower())
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "yes", "true", "on", "enabled"}


def _document_error_message(error: BaseException) -> str:
    detail = _error_detail(error)
    normalized = detail.casefold()
    if any(token in normalized for token in ("not-authorized", "unauthorized", "forbidden")):
        return _("CUPS denied access to the retained file. Check the username and password.")
    if any(token in normalized for token in ("not-found", "not found", "gone")):
        return _("CUPS no longer has the retained file for this job.")
    return _("CUPS could not provide the retained file: {detail}").format(detail=detail)


def _error_detail(error: BaseException) -> str:
    values = [str(value).strip() for value in getattr(error, "args", ()) if str(value).strip()]
    return " · ".join(values) or str(error).strip() or _("unknown CUPS error")
