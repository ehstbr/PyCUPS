from __future__ import annotations

import stat
import unittest

from print_archive.core.temp_store import PrivateTempStore


class TempStoreTests(unittest.TestCase):
    def test_private_store_is_removed(self) -> None:
        store = PrivateTempStore(prefix="print-archive-test-")
        root = store.root
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        store.path("secret.pdf").write_bytes(b"secret")

        store.cleanup()

        self.assertFalse(root.exists())
        store.cleanup()


if __name__ == "__main__":
    unittest.main()

