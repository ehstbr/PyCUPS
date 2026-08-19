from __future__ import annotations

import subprocess
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from print_archive.core.cups_service import (
    AuthenticationCanceledError,
    CupsRestartError,
    CupsService,
    CupsServiceError,
)
from print_archive.core.onboarding import SUGGESTED_RETENTION
from print_archive.core.page_ranges import parse_page_range
from print_archive.core.temp_store import PrivateTempStore
from print_archive.models import (
    CupsServerSettings,
    PreparedJob,
    PrintJob,
    RetrievedDocument,
)


class FakeCups:
    password_callback: object | None = None
    user = "desktop-user"

    @classmethod
    def setPasswordCB2(cls, callback: object | None) -> None:
        cls.password_callback = callback

    @classmethod
    def getUser(cls) -> str:
        return cls.user

    @classmethod
    def setUser(cls, user: str) -> None:
        cls.user = user


class FakeConnection:
    def __init__(self) -> None:
        self.restarted: list[int] = []
        self.printed: list[tuple[str, str, str, dict[str, str]]] = []
        self.purged: list[int] = []

    def getJobs(self, **kwargs: object) -> dict[int, dict[str, object]]:
        if kwargs["which_jobs"] == "completed":
            return {
                14: {
                    "job-id": 14,
                    "job-name": "Invoice",
                    "job-originating-user-name": "alice",
                    "job-printer-uri": "ipp://localhost/printers/Office%20Laser",
                    "job-state": 9,
                    "job-preserved": True,
                    "job-media-sheets": 10,
                    "time-at-creation": 1_700_000_000,
                    "time-at-completed": 1_700_000_100,
                }
            }
        return {
            15: {
                "job-name": "Pending",
                "job-printer-uri": "ipp://localhost/printers/Office%20Laser",
                "job-state": 3,
                "time-at-creation": 1_700_000_200,
            }
        }

    def getPrinters(self) -> dict[str, dict[str, object]]:
        return {"Office Laser": {}, "PDF": {}}

    def getPrinterAttributes(self, **kwargs: object) -> dict[str, object]:
        return {
            "printer-make-and-model": "Test Laser",
            "media-supported": ["iso_a4_210x297mm", "na_letter_8.5x11in"],
            "media-default": "iso_a4_210x297mm",
            "print-scaling-supported": ["fit", "fill", "none"],
            "print-scaling-default": "fit",
        }

    def restartJob(self, job_id: int) -> None:
        self.restarted.append(job_id)

    def printFile(
        self, printer: str, filename: str, title: str, options: dict[str, str]
    ) -> int:
        self.printed.append((printer, filename, title, options))
        return 99

    def cancelJob(self, job_id: int, *, purge_job: bool) -> None:
        self.assert_purge = purge_job
        self.purged.append(job_id)


class ProtectedConnection(FakeConnection):
    def _require_authentication(self, resource: str) -> None:
        callback = FakeCups.password_callback
        if not callable(callback):
            raise RuntimeError("client-error-not-authorized")
        password = callback("Password for CUPS", self, "POST", resource)
        if FakeCups.user != "alice" or password != "secret":
            raise RuntimeError("client-error-not-authorized")

    def getDocument(
        self, printer_uri: str, job_id: int, document_number: int
    ) -> dict[str, object]:
        self.last_document_request = (printer_uri, job_id, document_number)
        self._require_authentication("/printers/Office%20Laser")
        source = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        source.close()
        make_pdf(Path(source.name), pages=10)
        return {
            "file": source.name,
            "document-name": "invoice.pdf",
            "document-format": "application/pdf",
        }

    def restartJob(self, job_id: int) -> None:
        self._require_authentication("/jobs/")
        super().restartJob(job_id)


def make_pdf(path: Path, pages: int = 10) -> None:
    writer = PdfWriter()
    for page in range(pages):
        writer.add_blank_page(width=100 + page, height=200)
    with path.open("wb") as output:
        writer.write(output)


def print_job() -> PrintJob:
    return PrintJob(
        14,
        "Invoice",
        "alice",
        "Office Laser",
        "ipp://localhost/printers/Office%20Laser",
        9,
        None,
        None,
        10,
        10,
        100,
        1,
        True,
        "application/pdf",
        {},
    )


class CupsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeCups.password_callback = None
        FakeCups.user = "desktop-user"
        self.connection = FakeConnection()
        self.store = PrivateTempStore(prefix="print-archive-test-")
        self.service = CupsService(
            cups_module=FakeCups,
            connection=self.connection,
            store=self.store,
        )

    def tearDown(self) -> None:
        self.service.close()

    def prepared_pdf(self) -> PreparedJob:
        path = self.store.path("ten.pdf")
        make_pdf(path)
        document = RetrievedDocument(1, "ten.pdf", "application/pdf", path, 10)
        return PreparedJob(print_job(), (document,), path, 10, "pdf")

    def test_lists_and_normalizes_all_job_states(self) -> None:
        jobs = self.service.list_jobs()
        self.assertEqual([job.job_id for job in jobs], [15, 14])
        self.assertEqual(jobs[1].printer, "Office Laser")
        self.assertEqual(jobs[1].pages, 10)
        self.assertEqual(jobs[1].state_label, "Completed")

    def test_exact_reprint_restarts_original(self) -> None:
        result = self.service.reprint(
            self.prepared_pdf(), printer="Office Laser", copies=1
        )
        self.assertTrue(result.restarted_original)
        self.assertEqual(self.connection.restarted, [14])
        self.assertFalse(self.connection.printed)

    def test_retrieves_job_after_cups_authentication_even_if_flag_is_false(self) -> None:
        self.service.close()
        self.connection = ProtectedConnection()
        self.store = PrivateTempStore(prefix="print-archive-test-")
        self.service = CupsService(
            cups_module=FakeCups,
            connection=self.connection,
            store=self.store,
        )
        prompts: list[tuple[str, str, str, str]] = []

        def authenticate(
            prompt: str, user: str, method: str, resource: str
        ) -> tuple[str, str]:
            prompts.append((prompt, user, method, resource))
            return "alice", "secret"

        self.service.set_auth_provider(authenticate)
        job = replace(print_job(), preserved=False)

        prepared = self.service.retrieve_job(job)

        self.assertEqual(prepared.preview_kind, "pdf")
        self.assertEqual(prepared.total_pages, 10)
        self.assertTrue(job.can_restart)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0][1:], ("desktop-user", "POST", "/printers/Office%20Laser"))
        self.assertIsNone(FakeCups.password_callback)
        self.assertEqual(FakeCups.user, "desktop-user")

    def test_authentication_cancel_is_reported_distinctly(self) -> None:
        self.service.close()
        self.connection = ProtectedConnection()
        self.store = PrivateTempStore(prefix="print-archive-test-")
        self.service = CupsService(
            cups_module=FakeCups,
            connection=self.connection,
            store=self.store,
        )
        self.service.set_auth_provider(lambda *_args: None)

        with self.assertRaises(AuthenticationCanceledError):
            self.service.retrieve_job(replace(print_job(), preserved=False))

    def test_exact_restart_uses_the_same_cups_authentication_flow(self) -> None:
        self.service.close()
        self.connection = ProtectedConnection()
        self.store = PrivateTempStore(prefix="print-archive-test-")
        self.service = CupsService(
            cups_module=FakeCups,
            connection=self.connection,
            store=self.store,
        )
        self.service.set_auth_provider(
            lambda _prompt, _user, _method, _resource: ("alice", "secret")
        )

        result = self.service.reprint(
            self.prepared_pdf(), printer="Office Laser", copies=1
        )

        self.assertTrue(result.restarted_original)
        self.assertEqual(self.connection.restarted, [14])

    def test_selected_pages_create_a_new_pdf_job(self) -> None:
        prepared = self.prepared_pdf()
        result = self.service.reprint(
            prepared,
            printer="Office Laser",
            copies=2,
            selection=parse_page_range("4", 10),
        )
        self.assertFalse(result.restarted_original)
        self.assertEqual(result.job_id, 99)
        self.assertEqual(result.page_description, "4")
        printer, filename, title, options = self.connection.printed[0]
        self.assertEqual(printer, "Office Laser")
        self.assertEqual(options, {"copies": "2"})
        self.assertEqual(len(PdfReader(filename).pages), 1)
        self.assertEqual(float(PdfReader(filename).pages[0].mediabox.width), 103.0)
        self.assertIn("Reprint of Invoice", title)

    def test_flexible_reprint_sends_media_and_scaling_to_cups(self) -> None:
        self.service.reprint(
            self.prepared_pdf(),
            printer="Office Laser",
            copies=1,
            preserve_original=False,
            media_keyword="iso_a4_210x297mm",
            scaling="fill",
        )
        self.assertFalse(self.connection.restarted)
        self.assertEqual(
            self.connection.printed[0][3],
            {
                "copies": "1",
                "media": "iso_a4_210x297mm",
                "print-scaling": "fill",
            },
        )

    def test_lists_destination_capabilities(self) -> None:
        printers, capabilities = self.service.list_reprint_destinations()
        self.assertEqual(printers, ["Office Laser", "PDF"])
        self.assertEqual(capabilities["Office Laser"].default_media.display_name, "A4")

    def test_raw_data_cannot_be_flexibly_resubmitted(self) -> None:
        raw_path = self.store.path("job.bin")
        raw_path.write_bytes(b"\x1b%-12345Xraw printer language")
        document = RetrievedDocument(
            1, "job.bin", "application/vnd.cups-raw", raw_path, None
        )
        prepared = PreparedJob(print_job(), (document,), raw_path, None, "raw")

        with self.assertRaises(CupsServiceError):
            self.service.reprint(prepared, printer="PDF", copies=1)

        self.assertFalse(self.connection.printed)

    def test_purge_all_jobs(self) -> None:
        count = self.service.purge_all_jobs()
        self.assertEqual(count, 2)
        self.assertEqual(self.connection.purged, [15, 14])

    def test_reads_cupsctl_values(self) -> None:
        def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                ["cupsctl"],
                0,
                "PreserveJobFiles=7776000\nPreserveJobHistory=Yes\nMaxJobs=0\n",
                "",
            )

        self.service._run = runner
        with patch("print_archive.core.cups_service.shutil.which", return_value="/usr/sbin/cupsctl"):
            settings = self.service.read_retention_settings()
        self.assertEqual(settings.files_days, 90)
        self.assertTrue(settings.history_unlimited)
        self.assertTrue(settings.max_jobs_unlimited)

    def test_reads_unlimited_file_retention(self) -> None:
        def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                ["cupsctl"],
                0,
                "PreserveJobFiles=Yes\nPreserveJobHistory=Yes\nMaxJobs=0\n",
                "",
            )

        self.service._run = runner
        with patch("print_archive.core.cups_service.shutil.which", return_value="/usr/sbin/cupsctl"):
            settings = self.service.read_retention_settings()
        self.assertTrue(settings.files_unlimited)
        self.assertIsNone(settings.files_days)

    def test_applies_validated_values_through_pkexec_helper(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        self.service._run = runner
        helper = self.store.path("apply-settings")
        helper.write_text("helper", encoding="utf-8")
        self.service.apply_retention_settings(
            files_days=None,
            history_days=None,
            max_jobs=None,
            helper_path=helper,
        )
        self.assertEqual(
            calls[0],
            ["pkexec", str(helper), "retention", "Yes", "Yes", "0"],
        )

    def test_onboarding_suggestion_maps_to_expected_cups_values(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        self.service._run = runner
        helper = self.store.path("apply-settings")
        helper.write_text("helper", encoding="utf-8")
        self.service.apply_retention_settings(
            files_days=SUGGESTED_RETENTION.files_days,
            history_days=SUGGESTED_RETENTION.history_days,
            max_jobs=SUGGESTED_RETENTION.max_jobs,
            helper_path=helper,
        )
        self.assertEqual(
            calls[0],
            ["pkexec", str(helper), "retention", "2592000", "7776000", "0"],
        )

    def test_reads_and_applies_global_server_settings(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            if command == ["/usr/sbin/cupsctl"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "WebInterface=Yes\n_debug_logging=0\n_remote_admin=1\n"
                    "_remote_any=0\n_share_printers=1\n_user_cancel_any=0\n",
                    "",
                )
            return subprocess.CompletedProcess(command, 0, "", "")

        self.service._run = runner
        helper = self.store.path("apply-settings")
        helper.write_text("helper", encoding="utf-8")
        with patch("print_archive.core.cups_service.shutil.which", return_value="/usr/sbin/cupsctl"):
            settings = self.service.read_server_settings()
        self.assertTrue(settings.web_interface)
        self.assertTrue(settings.remote_admin)
        self.assertTrue(settings.share_printers)
        self.assertFalse(settings.remote_any)
        self.service.apply_server_settings(settings, helper_path=helper)
        self.assertEqual(
            calls[-1],
            ["pkexec", str(helper), "server", "yes", "no", "yes", "no", "yes", "no"],
        )

    def test_waits_for_consecutive_fresh_cups_connections(self) -> None:
        first_ready = FakeConnection()
        second_ready = FakeConnection()
        final_ready = FakeConnection()

        class RestartingCups:
            outcomes: list[object] = [
                RuntimeError("connection refused"),
                first_ready,
                RuntimeError("scheduler reloading"),
                second_ready,
                final_ready,
            ]
            attempts = 0

            @classmethod
            def Connection(cls) -> FakeConnection:
                outcome = cls.outcomes[cls.attempts]
                cls.attempts += 1
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

        previous_connection = self.service.connection
        self.service.cups = RestartingCups
        self.service.wait_for_cups_ready(
            timeout=1,
            interval=0,
            initial_delay=0,
            stable_checks=2,
        )

        self.assertEqual(RestartingCups.attempts, 5)
        self.assertIsNot(self.service.connection, previous_connection)
        self.assertIs(self.service.connection, final_ready)

    def test_cups_restart_wait_times_out_without_releasing_stale_connection(self) -> None:
        class OfflineCups:
            @staticmethod
            def Connection() -> FakeConnection:
                raise RuntimeError("connection refused")

        previous_connection = self.service.connection
        self.service.cups = OfflineCups
        with self.assertRaises(CupsRestartError):
            self.service.wait_for_cups_ready(
                timeout=0,
                interval=0,
                initial_delay=0,
            )
        self.assertIs(self.service.connection, previous_connection)

    def test_cups_restart_wait_can_be_canceled_during_shutdown(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()
        with self.assertRaises(CupsRestartError):
            self.service.wait_for_cups_ready(
                timeout=30,
                interval=1,
                initial_delay=0,
                cancel_event=cancel_event,
            )

    def test_defaults_match_cups_documentation(self) -> None:
        defaults = self.service.cups_defaults()
        self.assertEqual(defaults.files_days, 1)
        self.assertTrue(defaults.history_unlimited)
        self.assertEqual(defaults.max_jobs, 500)


if __name__ == "__main__":
    unittest.main()
