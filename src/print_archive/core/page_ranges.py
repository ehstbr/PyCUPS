from __future__ import annotations

from dataclasses import dataclass

from ..util.i18n import _


class PageRangeError(ValueError):
    """Raised when a human page-range expression is invalid."""


@dataclass(frozen=True, slots=True)
class PageSelection:
    pages: tuple[int, ...]
    total_pages: int

    @property
    def is_all(self) -> bool:
        return self.pages == tuple(range(1, self.total_pages + 1))

    @property
    def label(self) -> str:
        if self.is_all:
            return _("all pages")
        return compact_page_range(self.pages)


def parse_page_range(expression: str, total_pages: int) -> PageSelection:
    """Parse values such as ``3``, ``2-5`` and ``1,4,7-10``.

    Page numbers are one-based. Duplicates are removed and the resulting pages
    are returned in document order; this makes the output predictable and
    avoids accidentally printing a page twice.
    """
    if total_pages < 1:
        raise PageRangeError(_("The document has no printable pages."))
    text = expression.strip()
    if not text:
        raise PageRangeError(_("Enter at least one page number."))

    selected: set[int] = set()
    for token in text.split(","):
        part = token.strip()
        if not part:
            raise PageRangeError(_("There is an empty item in the page range."))
        if "-" in part:
            if part.count("-") != 1:
                raise PageRangeError(_("Invalid range: {range}.").format(range=part))
            first_text, last_text = (piece.strip() for piece in part.split("-", 1))
            first = _parse_page(first_text, total_pages)
            last = _parse_page(last_text, total_pages)
            if first > last:
                raise PageRangeError(_("Range {range} is reversed.").format(range=part))
            selected.update(range(first, last + 1))
        else:
            selected.add(_parse_page(part, total_pages))

    return PageSelection(tuple(sorted(selected)), total_pages)


def all_pages(total_pages: int) -> PageSelection:
    if total_pages < 1:
        raise PageRangeError(_("The document has no printable pages."))
    return PageSelection(tuple(range(1, total_pages + 1)), total_pages)


def compact_page_range(pages: tuple[int, ...] | list[int]) -> str:
    if not pages:
        return ""
    ordered = sorted(set(pages))
    groups: list[str] = []
    start = previous = ordered[0]
    for page in ordered[1:]:
        if page == previous + 1:
            previous = page
            continue
        groups.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = page
    groups.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(groups)


def _parse_page(value: str, total_pages: int) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError) as error:
        raise PageRangeError(_("Invalid page number: {value}.").format(value=value or "?")) from error
    if page < 1 or page > total_pages:
        raise PageRangeError(
            _("Page {page} is outside the document (1-{total}).").format(
                page=page, total=total_pages
            )
        )
    return page
