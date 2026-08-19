from __future__ import annotations

import gettext
import os
from pathlib import Path


DOMAIN = "print-archive"
_translation: gettext.NullTranslations = gettext.NullTranslations()


def _(message: str) -> str:
    return _translation.gettext(message)


def setup_gettext() -> gettext.NullTranslations:
    global _translation
    locale_dir = os.environ.get("PRINT_ARCHIVE_LOCALE_DIR")
    if locale_dir is None:
        source_locale = Path(__file__).resolve().parents[3] / "locale"
        locale_dir = str(source_locale if source_locale.is_dir() else Path("/usr/share/locale"))
    _translation = gettext.translation(DOMAIN, locale_dir, fallback=True)
    _translation.install()
    return _translation
