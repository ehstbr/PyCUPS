from __future__ import annotations

import sys

from .application import PrintArchiveApplication


def main() -> int:
    return PrintArchiveApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())

