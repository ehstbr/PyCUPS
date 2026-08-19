from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from ..models import MediaOption, PrinterCapabilities


_MEDIA_DIMENSIONS = re.compile(
    r"(?:^|_)(?P<width>[0-9]+(?:\.[0-9]+)?)x"
    r"(?P<height>[0-9]+(?:\.[0-9]+)?)(?P<unit>mm|in)(?:_|$)",
    re.IGNORECASE,
)

_MEDIA_NAMES = {
    "iso_a3_297x420mm": "A3",
    "iso_a4_210x297mm": "A4",
    "iso_a5_148x210mm": "A5",
    "iso_a6_105x148mm": "A6",
    "iso_b5_176x250mm": "B5",
    "na_letter_8.5x11in": "Letter",
    "na_legal_8.5x14in": "Legal",
    "na_executive_7.25x10.5in": "Executive",
    "oe_photo-l_3.5x5in": "Photo 3.5 × 5 in",
    "oe_photo-4x6_4x6in": "Photo 4 × 6 in",
}

_SCALING_ORDER = ("auto", "auto-fit", "fit", "fill", "none")


def parse_printer_capabilities(
    printer: str,
    attributes: Mapping[str, Any],
) -> PrinterCapabilities:
    """Normalize IPP media/scaling attributes into stable UI models."""

    media_by_keyword: dict[str, MediaOption] = {}
    collections = _as_collection_list(attributes.get("media-col-database"))
    collections.extend(_as_collection_list(attributes.get("media-col-ready")))
    default_collection = _as_collection(attributes.get("media-col-default"))
    if default_collection:
        collections.insert(0, default_collection)

    for collection in collections:
        media = _media_from_collection(collection)
        if not media:
            continue
        existing = media_by_keyword.get(media.keyword)
        if existing is None or (
            not existing.width_mm and media.width_mm and media.height_mm
        ):
            media_by_keyword[media.keyword] = media

    supported = _as_string_list(attributes.get("media-supported"))
    supported.extend(_as_string_list(attributes.get("media-ready")))
    default_media = _default_media_keyword(attributes, default_collection)
    if default_media:
        supported.insert(0, default_media)
    for keyword in supported:
        if keyword and keyword not in media_by_keyword:
            media_by_keyword[keyword] = media_from_keyword(keyword)

    media_options = tuple(
        sorted(
            media_by_keyword.values(),
            key=lambda item: (
                item.keyword != default_media,
                item.display_name.casefold(),
                item.keyword.casefold(),
            ),
        )
    )

    scaling_values = _as_string_list(attributes.get("print-scaling-supported"))
    scaling_supported = tuple(
        value for value in _SCALING_ORDER if value in set(scaling_values)
    )
    if not scaling_supported:
        scaling_supported = ("fit", "fill", "none")
    default_scaling = str(attributes.get("print-scaling-default") or "auto")
    if default_scaling not in scaling_supported:
        default_scaling = "fit" if "fit" in scaling_supported else scaling_supported[0]

    return PrinterCapabilities(
        printer=printer,
        make_model=str(attributes.get("printer-make-and-model") or ""),
        media_options=media_options,
        default_media_keyword=default_media,
        scaling_supported=scaling_supported,
        default_scaling=default_scaling,
    )


def media_from_keyword(keyword: str) -> MediaOption:
    normalized = keyword.strip()
    width_mm: float | None = None
    height_mm: float | None = None
    match = _MEDIA_DIMENSIONS.search(normalized)
    if match:
        width_mm = float(match.group("width"))
        height_mm = float(match.group("height"))
        if match.group("unit").lower() == "in":
            width_mm *= 25.4
            height_mm *= 25.4
        width_mm = round(width_mm, 2)
        height_mm = round(height_mm, 2)
    name = _MEDIA_NAMES.get(normalized)
    if not name:
        prefix = normalized.split("_", 1)[0].upper() if "_" in normalized else ""
        name = normalized.replace("_", " ").replace("-", " ").strip().title()
        if prefix in {"ISO", "NA", "OE", "JIS", "OM"}:
            name = name[len(prefix) :].strip()
    return MediaOption(normalized, name or normalized, width_mm, height_mm)


def _media_from_collection(collection: Mapping[str, Any]) -> MediaOption | None:
    keyword = str(collection.get("media-key") or collection.get("media-size-name") or "")
    dimensions = _as_collection(collection.get("media-size"))
    if not keyword and dimensions:
        x_dimension = _number(dimensions.get("x-dimension"))
        y_dimension = _number(dimensions.get("y-dimension"))
        if x_dimension and y_dimension:
            keyword = f"custom_{x_dimension / 100:g}x{y_dimension / 100:g}mm"
    if not keyword:
        return None

    base = media_from_keyword(keyword)
    width_mm = base.width_mm
    height_mm = base.height_mm
    if dimensions:
        x_dimension = _number(dimensions.get("x-dimension"))
        y_dimension = _number(dimensions.get("y-dimension"))
        if x_dimension and y_dimension:
            width_mm = round(x_dimension / 100.0, 2)
            height_mm = round(y_dimension / 100.0, 2)

    return MediaOption(
        keyword=keyword,
        display_name=base.display_name,
        width_mm=width_mm,
        height_mm=height_mm,
        margin_top_mm=_number(collection.get("media-top-margin")) / 100.0,
        margin_right_mm=_number(collection.get("media-right-margin")) / 100.0,
        margin_bottom_mm=_number(collection.get("media-bottom-margin")) / 100.0,
        margin_left_mm=_number(collection.get("media-left-margin")) / 100.0,
    )


def _default_media_keyword(
    attributes: Mapping[str, Any],
    default_collection: Mapping[str, Any] | None,
) -> str | None:
    if default_collection:
        keyword = default_collection.get("media-key") or default_collection.get("media-size-name")
        if keyword:
            return str(keyword)
    value = attributes.get("media-default")
    if isinstance(value, (tuple, list)):
        value = value[0] if value else None
    return str(value) if value else None


def _as_collection(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _as_collection_list(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if item]
    return [str(value)]


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return 0.0
