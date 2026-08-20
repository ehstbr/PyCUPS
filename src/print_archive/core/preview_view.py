from __future__ import annotations


MIN_ZOOM_PERCENT = 1.0
MAX_ZOOM_PERCENT = 500.0
ZOOM_STEP_PERCENT = 10.0


def normalize_rotation(degrees: int) -> int:
    """Return one of the four right-angle rotations used by the preview."""

    return (round(degrees / 90) * 90) % 360


def rotated_dimensions(width: int, height: int, rotation: int) -> tuple[int, int]:
    rotation = normalize_rotation(rotation)
    if rotation in {90, 270}:
        return height, width
    return width, height


def clamp_zoom(percent: float) -> float:
    return max(MIN_ZOOM_PERCENT, min(MAX_ZOOM_PERCENT, float(percent)))


def stepped_zoom(percent: float, steps: int) -> float:
    return clamp_zoom(percent + (steps * ZOOM_STEP_PERCENT))


def fit_zoom_percent(
    image_width: int,
    image_height: int,
    viewport_width: int,
    viewport_height: int,
    *,
    padding: int = 24,
) -> float:
    """Calculate a bounded zoom that keeps the whole image in the viewport."""

    if min(image_width, image_height, viewport_width, viewport_height) <= 0:
        return 100.0
    available_width = max(1, viewport_width - padding)
    available_height = max(1, viewport_height - padding)
    return clamp_zoom(
        min(
            available_width / image_width,
            available_height / image_height,
        )
        * 100.0
    )


def zoomed_dimensions(width: int, height: int, percent: float) -> tuple[int, int]:
    factor = clamp_zoom(percent) / 100.0
    return max(1, round(width * factor)), max(1, round(height * factor))
