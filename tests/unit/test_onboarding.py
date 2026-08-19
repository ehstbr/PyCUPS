from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from print_archive.core.onboarding import (
    SUGGESTED_RETENTION,
    OnboardingStateStore,
)


class OnboardingTests(unittest.TestCase):
    def test_suggested_profile_balances_recovery_and_privacy(self) -> None:
        self.assertEqual(SUGGESTED_RETENTION.files_days, 30)
        self.assertEqual(SUGGESTED_RETENTION.history_days, 90)
        self.assertIsNone(SUGGESTED_RETENTION.max_jobs)

    def test_state_is_incomplete_until_the_flow_is_explicitly_finished(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pycups" / "state.json"
            store = OnboardingStateStore(path)

            self.assertFalse(store.is_complete())
            store.mark_complete()
            self.assertTrue(store.is_complete())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_or_incompatible_state_reopens_onboarding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("not json", encoding="utf-8")
            self.assertFalse(OnboardingStateStore(path).is_complete())

            path.write_text(
                json.dumps({"schema_version": 2, "onboarding_completed": True}),
                encoding="utf-8",
            )
            self.assertFalse(OnboardingStateStore(path).is_complete())


if __name__ == "__main__":
    unittest.main()
