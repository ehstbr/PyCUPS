from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SuggestedRetention:
    """Balanced first-run proposal; never applied without explicit consent."""

    files_days: int = 30
    history_days: int = 90
    max_jobs: int | None = None


SUGGESTED_RETENTION = SuggestedRetention()


def default_state_path() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".config"
    if not root.is_absolute():
        root = Path.home() / ".config"
    return root / "pycups" / "state.json"


class OnboardingStateStore:
    """Persist only whether the local welcome flow has been completed."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()

    def is_complete(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        return bool(
            isinstance(payload, dict)
            and payload.get("schema_version") == STATE_SCHEMA_VERSION
            and payload.get("onboarding_completed") is True
        )

    def mark_complete(self) -> None:
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = {
            "schema_version": STATE_SCHEMA_VERSION,
            "onboarding_completed": True,
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=directory,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, separators=(",", ":"))
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self.path)
            self.path.chmod(0o600)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
