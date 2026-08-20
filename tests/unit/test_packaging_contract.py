from __future__ import annotations

import unittest
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PackagingContractTests(unittest.TestCase):
    def test_public_brand_is_pycups_without_breaking_installed_identifiers(self) -> None:
        package = (PROJECT_ROOT / "src/print_archive/__init__.py").read_text(
            encoding="utf-8"
        )
        desktop = (
            PROJECT_ROOT / "data/com.eduhcommerce.PrintArchive.desktop"
        ).read_text(encoding="utf-8")
        metainfo = (
            PROJECT_ROOT / "data/com.eduhcommerce.PrintArchive.metainfo.xml"
        ).read_text(encoding="utf-8")
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        public_sources = "\n".join(
            (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
            for relative_path in (
                "src/print_archive/application.py",
                "src/print_archive/ui/about.py",
                "src/print_archive/ui/main_window.py",
                "src/print_archive/ui/settings.py",
                "src/print_archive/ui/update_window.py",
                "README.md",
                "README.pt-BR.md",
            )
        )

        self.assertIn('APP_NAME = "PyCUPS"', package)
        self.assertIn('APP_TAGLINE = "CUPS Archive"', package)
        self.assertIn("Name=PyCUPS", desktop)
        self.assertIn("GenericName=CUPS Archive", desktop)
        self.assertIn("<name>PyCUPS</name>", metainfo)
        self.assertIn("CUPS Archive for retained print jobs", metainfo)
        self.assertNotIn("Print Archive", public_sources)

        self.assertIn('APP_ID = "com.eduhcommerce.PrintArchive"', package)
        self.assertIn('name = "print-archive"', pyproject)
        self.assertIn('print-archive = "print_archive.__main__:main"', pyproject)

    def test_installation_scripts_never_change_cups_retention(self) -> None:
        forbidden = (
            "cupsctl",
            "apply-settings",
            "PreserveJobFiles",
            "PreserveJobHistory",
            "MaxJobs",
        )
        for relative_path in (
            "packaging/debian/postinst",
            "packaging/debian/postrm",
        ):
            content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=relative_path, token=token):
                    self.assertNotIn(token, content)

    def test_onboarding_is_three_step_explicit_and_reopenable(self) -> None:
        application = (PROJECT_ROOT / "src/print_archive/application.py").read_text(
            encoding="utf-8"
        )
        onboarding = (
            PROJECT_ROOT / "src/print_archive/ui/onboarding.py"
        ).read_text(encoding="utf-8")
        main_window = (
            PROJECT_ROOT / "src/print_archive/ui/main_window.py"
        ).read_text(encoding="utf-8")

        self.assertIn("not self.onboarding_state.is_complete()", application)
        self.assertIn('(\"onboarding\", lambda *_args:', application)
        self.assertIn('menu_model.append(_("Welcome and initial setup")', main_window)
        self.assertIn('self.pages.add_named(self._build_welcome_page(), "welcome")', onboarding)
        self.assertIn('self.pages.add_named(self._build_retention_page(), "retention")', onboarding)
        self.assertIn('self.pages.add_named(self._build_finish_page(), "finish")', onboarding)
        self.assertIn('_("Skip without changes")', onboarding)
        self.assertIn('_("Apply and continue")', onboarding)
        self.assertIn("self.state_store.mark_complete()", onboarding)

    def test_onboarding_suggestion_is_never_applied_implicitly(self) -> None:
        onboarding = (
            PROJECT_ROOT / "src/print_archive/ui/onboarding.py"
        ).read_text(encoding="utf-8")
        constructor = onboarding.split("    def __init__", 1)[1].split(
            "    @staticmethod", 1
        )[0]
        apply_method = onboarding.split("    def _apply_retention", 1)[1].split(
            "    def _proposed_values", 1
        )[0]

        self.assertNotIn("apply_retention_settings", constructor)
        self.assertIn("apply_retention_settings", apply_method)
        self.assertIn("SUGGESTED_RETENTION.files_days", onboarding)
        self.assertIn("SUGGESTED_RETENTION.history_days", onboarding)
        self.assertIn("SUGGESTED_RETENTION.max_jobs is None", onboarding)

    def test_onboarding_heroes_do_not_create_nested_scrollers(self) -> None:
        onboarding = (
            PROJECT_ROOT / "src/print_archive/ui/onboarding.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("Adw.StatusPage", onboarding)
        self.assertIn("def _compact_hero(", onboarding)
        self.assertIn("vscrollbar_policy=Gtk.PolicyType.AUTOMATIC", onboarding)
        self.assertEqual(onboarding.count("Gtk.ScrolledWindow("), 1)

    def test_settings_have_no_suggested_retention_profile(self) -> None:
        settings = (PROJECT_ROOT / "src/print_archive/ui/settings.py").read_text(
            encoding="utf-8"
        )
        service = (PROJECT_ROOT / "src/print_archive/core/cups_service.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Use the agreed configuration", settings)
        self.assertNotIn("recommended_settings", service)
        self.assertIn("read_retention_settings", settings)
        self.assertIn("apply_retention_settings", settings)

    def test_settings_are_global_and_split_into_three_pages(self) -> None:
        settings = (PROJECT_ROOT / "src/print_archive/ui/settings.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('title=_("Retention")', settings)
        self.assertIn('title=_("Server")', settings)
        self.assertIn('title=_("Maintenance")', settings)
        self.assertIn("Global CUPS settings only", settings)
        self.assertNotIn("getPrinterAttributes", settings)

    def test_settings_apply_actions_stay_outside_scrolling_content(self) -> None:
        settings = (PROJECT_ROOT / "src/print_archive/ui/settings.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("toolbar.add_bottom_bar(self.footer_stack)", settings)
        self.assertIn("_build_retention_footer", settings)
        self.assertIn("_build_server_footer", settings)
        self.assertNotIn('title=_("Current retention configuration")', settings)
        self.assertNotIn('title=_("Current global server configuration")', settings)

    def test_cups_restart_wait_blocks_all_app_windows_and_refreshes(self) -> None:
        application = (PROJECT_ROOT / "src/print_archive/application.py").read_text(
            encoding="utf-8"
        )
        dialog = (
            PROJECT_ROOT / "src/print_archive/ui/cups_restart.py"
        ).read_text(encoding="utf-8")
        settings = (PROJECT_ROOT / "src/print_archive/ui/settings.py").read_text(
            encoding="utf-8"
        )
        onboarding = (
            PROJECT_ROOT / "src/print_archive/ui/onboarding.py"
        ).read_text(encoding="utf-8")
        main_window = (
            PROJECT_ROOT / "src/print_archive/ui/main_window.py"
        ).read_text(encoding="utf-8")
        service = (
            PROJECT_ROOT / "src/print_archive/core/cups_service.py"
        ).read_text(encoding="utf-8")
        meson = (PROJECT_ROOT / "meson.build").read_text(encoding="utf-8")

        self.assertIn("def wait_for_cups_restart(", application)
        self.assertIn("self.service.wait_for_cups_ready", application)
        self.assertIn("window.set_sensitive(False)", application)
        self.assertIn('action.set_enabled(False)', application)
        self.assertIn("self.window.set_cups_restart_in_progress(True)", application)
        self.assertIn("GLib.timeout_add_seconds(", application)
        self.assertIn("def _continue_cups_restart_wait(", application)
        self.assertIn("set_deletable(False)", dialog)
        self.assertIn('_("Restarting CUPS…")', dialog)
        self.assertIn('_("Try again")', dialog)
        self.assertIn('_("Close PyCUPS")', dialog)
        self.assertIn("It will try again automatically", dialog)
        self.assertEqual(settings.count("self.wait_for_cups_restart("), 2)
        self.assertEqual(onboarding.count("self.wait_for_cups_restart("), 1)
        self.assertIn("or self._cups_restart_in_progress", main_window)
        self.assertIn("def wait_for_cups_ready(", service)
        self.assertIn("candidate = self.cups.Connection()", service)
        self.assertIn("candidate.getPrinters()", service)
        self.assertIn("'src/print_archive/ui/cups_restart.py'", meson)

    def test_reprint_preview_is_the_left_resizable_pane(self) -> None:
        source = (PROJECT_ROOT / "src/print_archive/ui/reprint_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("paned.set_start_child(self._build_preview())", source)
        self.assertIn("paned.set_end_child(self._build_options())", source)
        self.assertIn("paned.set_resize_start_child(True)", source)
        self.assertIn("paned.set_resize_end_child(False)", source)

    def test_file_retention_supports_an_explicit_unlimited_mode(self) -> None:
        settings = (PROJECT_ROOT / "src/print_archive/ui/settings.py").read_text(
            encoding="utf-8"
        )
        service = (PROJECT_ROOT / "src/print_archive/core/cups_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self.files_unlimited = Adw.SwitchRow", settings)
        self.assertIn('subtitle="PreserveJobFiles=Yes"', settings)
        self.assertIn('"Yes" if files_days is None', service)

    def test_release_manifest_matches_package_and_uses_utc(self) -> None:
        manifest = json.loads((PROJECT_ROOT / "version.json").read_text(encoding="utf-8"))
        package = (PROJECT_ROOT / "src/print_archive/__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(f'VERSION = "{manifest["version"]}"', package)
        self.assertEqual(manifest["schema_version"], 1)
        self.assertTrue(manifest["released_at"].endswith("Z"))
        self.assertIsInstance(manifest["mandatory"], bool)

    def test_privileged_helper_has_explicit_bounded_modes(self) -> None:
        helper = (PROJECT_ROOT / "packaging/apply-settings").read_text(encoding="utf-8")
        self.assertIn('mode="$1"', helper)
        self.assertIn('"$mode" = "retention"', helper)
        self.assertIn('"$mode" = "server"', helper)
        self.assertIn('preserve_files" != "Yes"', helper)
        self.assertIn("yes|no", helper)

    def test_printer_filter_is_ready_before_history_rows_are_added(self) -> None:
        source = (PROJECT_ROOT / "src/print_archive/ui/main_window.py").read_text(
            encoding="utf-8"
        )
        jobs_loaded = source.split("    def _jobs_loaded", 1)[1].split(
            "    def _jobs_failed", 1
        )[0]
        self.assertLess(
            jobs_loaded.index("self.printer_filter.update_printers"),
            jobs_loaded.index("self.job_list.append"),
        )
        self.assertIn("self.job_list.invalidate_filter()", jobs_loaded)

    def test_target_paper_selector_cannot_compress_its_row_label(self) -> None:
        source = (PROJECT_ROOT / "src/print_archive/ui/reprint_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_MEDIA_SELECTOR_WIDTH_CHARS = 24", source)
        self.assertIn("Pango.EllipsizeMode.END", source)
        self.assertIn("max_width_chars=width_chars", source)
        self.assertIn(
            "_bound_dropdown_selection(self.media_dropdown, _MEDIA_SELECTOR_WIDTH_CHARS)",
            source,
        )
        self.assertIn("dropdown.set_list_factory(popup_factory)", source)
        self.assertIn("self.media_dropdown.set_tooltip_text(text)", source)

    def test_cups_restart_keeps_background_action_labels_stable(self) -> None:
        settings = (PROJECT_ROOT / "src/print_archive/ui/settings.py").read_text(
            encoding="utf-8"
        )
        onboarding = (
            PROJECT_ROOT / "src/print_archive/ui/onboarding.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("retention_apply_button.set_label", settings)
        self.assertNotIn("server_apply_button.set_label", settings)
        self.assertNotIn("next_button.set_label", onboarding)
        self.assertIn('_("Apply")', settings)
        self.assertIn('_("Start using {app_name}")', onboarding)
        self.assertIn("self.next_button.set_sensitive(False)", onboarding)

    def test_main_preview_has_visual_controls_only_in_the_history_viewer(self) -> None:
        main_window = (
            PROJECT_ROOT / "src/print_archive/ui/main_window.py"
        ).read_text(encoding="utf-8")
        reprint = (
            PROJECT_ROOT / "src/print_archive/ui/reprint_dialog.py"
        ).read_text(encoding="utf-8")
        meson = (PROJECT_ROOT / "meson.build").read_text(encoding="utf-8")

        for token in (
            "object-rotate-left-symbolic",
            "object-rotate-right-symbolic",
            "zoom-out-symbolic",
            "zoom-in-symbolic",
            "zoom-fit-best-symbolic",
            "zoom-original-symbolic",
            "Gtk.EventControllerScroll.new",
            "Gtk.GestureDrag.new",
            "Gtk.DrawingArea(",
            'connect("resize", self._preview_view_resized)',
            "def _preview_scrolled(",
            "def _preview_drag_update(",
            "self.preview_controls.append(self.page_controls)",
            "self.page_separator.set_visible(visible)",
        ):
            self.assertIn(token, main_window)
        self.assertNotIn("content.append(self.page_controls)", main_window)
        self.assertNotIn("object-rotate-left-symbolic", reprint)
        self.assertNotIn("zoom-fit-best-symbolic", reprint)
        self.assertIn("src/print_archive/core/preview_view.py", meson)

    def test_primary_job_actions_have_icons_and_concise_labels(self) -> None:
        source = (PROJECT_ROOT / "src/print_archive/ui/main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('_("Export original")', source)
        self.assertIn('_("Reprint")', source)
        self.assertIn('"document-save-symbolic"', source)
        self.assertIn('"document-print-symbolic"', source)
        self.assertNotIn('_("Export original…")', source)
        self.assertNotIn('_("Reprint…")', source)

    def test_main_preview_registers_cairo_and_dynamic_rows_disable_markup(self) -> None:
        main_window = (
            PROJECT_ROOT / "src/print_archive/ui/main_window.py"
        ).read_text(encoding="utf-8")
        update_window = (
            PROJECT_ROOT / "src/print_archive/ui/update_window.py"
        ).read_text(encoding="utf-8")
        control = (
            PROJECT_ROOT / "packaging/debian/binary-control.in"
        ).read_text(encoding="utf-8")
        launcher = (PROJECT_ROOT / "run.sh").read_text(encoding="utf-8")

        self.assertIn('gi.require_foreign("cairo")', main_window)
        self.assertIn('gi.require_foreign("cairo")', launcher)
        self.assertIn("python3-gi-cairo", control)
        self.assertIn("python3-gi-cairo", launcher)

        job_row = main_window.split("    def _job_row(", 1)[1].split(
            "    def _filter_job_row(", 1
        )[0]
        self.assertIn("use_markup=False", job_row)
        self.assertIn("row.set_title(job.title)", job_row)
        self.assertIn("Adw.ActionRow(use_markup=False)", update_window)

    def test_github_readmes_link_translations_and_packaged_screenshots(self) -> None:
        english = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        portuguese = (PROJECT_ROOT / "README.pt-BR.md").read_text(encoding="utf-8")
        screenshots = (
            "main-window.png",
            "reprint-preview.png",
            "onboarding-welcome.png",
            "onboarding-retention.png",
            "onboarding-complete.png",
            "settings-retention.png",
            "settings-server.png",
            "settings-maintenance.png",
        )

        self.assertIn('href="README.pt-BR.md"', english)
        self.assertIn('href="README.md"', portuguese)
        self.assertIn("## When PyCUPS can be useful", english)
        self.assertIn("## Em quais situações o PyCUPS pode ser útil", portuguese)
        self.assertIn("CONTRIBUTING.md#translations", english)
        self.assertIn("CONTRIBUTING.md#translations", portuguese)
        for filename in screenshots:
            path = PROJECT_ROOT / "docs/screenshots" / filename
            self.assertTrue(path.is_file(), filename)
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), filename)
            self.assertIn(f"docs/screenshots/{filename}", english)
            self.assertIn(f"docs/screenshots/{filename}", portuguese)
        for relative_path in (
            ".github/workflows/ci.yml",
            ".github/dependabot.yml",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".editorconfig",
            ".gitattributes",
            ".gitignore",
            "SECURITY.md",
            "SUPPORT.md",
        ):
            self.assertTrue((PROJECT_ROOT / relative_path).is_file(), relative_path)


if __name__ == "__main__":
    unittest.main()
