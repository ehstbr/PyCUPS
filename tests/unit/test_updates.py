from __future__ import annotations

import json
import unittest

from print_archive.core.updates import (
    SemanticVersion,
    UpdateChecker,
    UpdateManifestError,
    evaluate_update,
    parse_update_manifest,
)


def manifest_bytes(**changes: object) -> bytes:
    payload: dict[str, object] = {
        "schema_version": 1,
        "version": "0.1.4",
        "mandatory": False,
        "released_at": "2026-08-19T22:00:00Z",
        "summary": "A tested update.",
        "changelog": ["One change", "Another change"],
    }
    payload.update(changes)
    return json.dumps(payload).encode("utf-8")


class FakeCancellable:
    def __init__(self) -> None:
        self.canceled = False

    def cancel(self) -> None:
        self.canceled = True


class ImmediateHttp:
    def __init__(self, status: int, data: bytes, error: Exception | None = None) -> None:
        self.status = status
        self.data = data
        self.error = error

    def request(self, _method: str, _url: str, callback: object, **_kwargs: object) -> FakeCancellable:
        callback(self.status, self.data, self.error)
        return FakeCancellable()


class UpdateTests(unittest.TestCase):
    def test_semver_comparison_handles_prereleases(self) -> None:
        self.assertLess(SemanticVersion.parse("1.0.0-rc.1"), SemanticVersion.parse("1.0.0"))
        self.assertGreater(SemanticVersion.parse("1.2.0"), SemanticVersion.parse("1.1.99"))

    def test_valid_manifest_is_newer_than_installed_version(self) -> None:
        result = evaluate_update(manifest_bytes(), current_version="0.1.3")
        self.assertTrue(result.update_available)
        self.assertEqual(result.latest.version_text, "0.1.4")
        self.assertEqual(result.latest.released_at_utc_text, "2026-08-19 22:00 UTC")

    def test_manifest_requires_an_explicit_utc_z_timestamp(self) -> None:
        with self.assertRaises(UpdateManifestError):
            parse_update_manifest(
                manifest_bytes(released_at="2026-08-19T19:00:00-03:00")
            )

    def test_checker_reports_http_failure_without_raising(self) -> None:
        results = []
        checker = UpdateChecker(http=ImmediateHttp(503, b""))
        checker.check(results.append)
        self.assertEqual(results[0].error, "HTTP status 503")


if __name__ == "__main__":
    unittest.main()
