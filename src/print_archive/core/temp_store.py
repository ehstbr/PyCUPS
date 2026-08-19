from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class PrivateTempStore:
    """Per-process storage for sensitive spool copies and previews."""

    def __init__(self, prefix: str = "print-archive-") -> None:
        self.root = Path(tempfile.mkdtemp(prefix=prefix))
        self.root.chmod(0o700)
        self._closed = False

    def path(self, filename: str) -> Path:
        if self._closed:
            raise RuntimeError("Temporary store is closed.")
        safe_name = Path(filename).name or "document"
        return self.root / safe_name

    def cleanup(self) -> None:
        if self._closed:
            return
        shutil.rmtree(self.root, ignore_errors=True)
        self._closed = True

    def __enter__(self) -> "PrivateTempStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.cleanup()

