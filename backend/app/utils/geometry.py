"""
Geometry and Coordinate Utilities

Provides functions for handling UI bounds, coordinates, and geometric calculations
across different platforms (Android, iOS, macOS, Web).
"""

import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)


class Bounds(NamedTuple):
    """Represents a rectangular bounds: (x1, y1, x2, y2)"""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        """Calculate width of bounds."""
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        """Calculate height of bounds."""
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[int, int]:
        """Calculate center point of bounds."""
        return (self.x1 + self.width // 2, self.y1 + self.height // 2)

    @property
    def area(self) -> int:
        """Calculate area of bounds."""
        return self.width * self.height

    def contains(self, x: int, y: int) -> bool:
        """Check if point (x, y) is within bounds."""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def intersects(self, other: "Bounds") -> bool:
        """Check if this bounds intersects with another."""
        return not (
            self.x2 < other.x1
            or other.x2 < self.x1
            or self.y2 < other.y1
            or other.y2 < self.y1
        )

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "width": self.width,
            "height": self.height,
        }


def parse_bounds(bounds_str: str) -> Bounds | None:
    """
    Parse bounds string into Bounds tuple.

    Supports formats:
    - Android: "[x1,y1][x2,y2]" (e.g., "[100,200][300,400]")
    - Comma-separated: "x1,y1,x2,y2" (e.g., "100,200,300,400")

    Args:
        bounds_str: String representation of bounds

    Returns:
        Bounds tuple or None if parsing fails

    Examples:
        >>> parse_bounds("[100,200][300,400]")
        Bounds(x1=100, y1=200, x2=300, y2=400)
        >>> parse_bounds("10,20,30,40")
        Bounds(x1=10, y1=20, x2=30, y2=40)
    """
    if not bounds_str or not isinstance(bounds_str, str):
        return None

    bounds_str = bounds_str.strip()

    # Try Android format: [x1,y1][x2,y2]
    android_pattern = r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]"
    match = re.match(android_pattern, bounds_str)
    if match:
        return Bounds(
            x1=int(match.group(1)),
            y1=int(match.group(2)),
            x2=int(match.group(3)),
            y2=int(match.group(4)),
        )

    # Try comma-separated format: x1,y1,x2,y2
    try:
        parts = [int(x.strip()) for x in bounds_str.split(",")]
        if len(parts) == 4:
            return Bounds(x1=parts[0], y1=parts[1], x2=parts[2], y2=parts[3])
    except ValueError:
        pass

    logger.debug(f"Failed to parse bounds string: {bounds_str}")
    return None


def format_bounds(bounds: Bounds | tuple[int, int, int, int]) -> str:
    """
    Format bounds to Android-style string.

    Args:
        bounds: Bounds tuple or (x1, y1, x2, y2) tuple

    Returns:
        Formatted string "[x1,y1][x2,y2]"
    """
    if isinstance(bounds, tuple):
        bounds = Bounds(*bounds)
    return f"[{bounds.x1},{bounds.y1}][{bounds.x2},{bounds.y2}]"


def normalize_coordinates(
    x: int | float | None, y: int | float | None, screen_w: int, screen_h: int
) -> tuple[int | None, int | None]:
    """
    Convert relative coordinates (0.0-1.0) to absolute pixel coordinates.

    If coordinates are already integers, they are returned as-is.
    If coordinates are floats (0.0-1.0), they are multiplied by screen dimensions.

    Args:
        x: X coordinate (float 0.0-1.0 or int pixels)
        y: Y coordinate (float 0.0-1.0 or int pixels)
        screen_w: Screen width in pixels
        screen_h: Screen height in pixels

    Returns:
        Tuple of (x, y) in pixel coordinates, or (None, None) if input is None

    Examples:
        >>> normalize_coordinates(0.5, 0.5, 1000, 2000)
        (500, 1000)
        >>> normalize_coordinates(100, 200, 1000, 2000)
        (100, 200)
        >>> normalize_coordinates(None, 0.5, 1000, 2000)
        (None, 1000)
    """
    if x is None or y is None:
        return x, y

    # If already integers, return as-is
    if isinstance(x, int) and isinstance(y, int):
        return x, y

    # Convert floats to pixels
    nx = int(x * screen_w) if isinstance(x, float) else int(x)
    ny = int(y * screen_h) if isinstance(y, float) else int(y)

    return nx, ny


def denormalize_coordinates(x: int, y: int, screen_w: int, screen_h: int) -> tuple[float, float]:
    """
    Convert absolute pixel coordinates to relative (0.0-1.0).

    Args:
        x: X coordinate in pixels
        y: Y coordinate in pixels
        screen_w: Screen width in pixels
        screen_h: Screen height in pixels

    Returns:
        Tuple of (x, y) as floats 0.0-1.0
    """
    return x / screen_w, y / screen_h


def get_bounds_center(bounds: Bounds | tuple[int, int, int, int]) -> tuple[int, int]:
    """
    Get the center point of bounds.

    Args:
        bounds: Bounds tuple or (x1, y1, x2, y2)

    Returns:
        (center_x, center_y)
    """
    if isinstance(bounds, tuple):
        bounds = Bounds(*bounds)
    return bounds.center


def is_point_in_bounds(x: int, y: int, bounds: Bounds | tuple[int, int, int, int]) -> bool:
    """
    Check if a point is within bounds.

    Args:
        x: X coordinate
        y: Y coordinate
        bounds: Bounds to check against

    Returns:
        True if point is within bounds
    """
    if isinstance(bounds, tuple):
        bounds = Bounds(*bounds)
    return bounds.contains(x, y)


def calculate_intersection_area(
    bounds1: Bounds | tuple[int, int, int, int],
    bounds2: Bounds | tuple[int, int, int, int],
) -> int:
    """
    Calculate the intersection area of two bounds.

    Args:
        bounds1: First bounds
        bounds2: Second bounds

    Returns:
        Intersection area in square pixels
    """
    if isinstance(bounds1, tuple):
        bounds1 = Bounds(*bounds1)
    if isinstance(bounds2, tuple):
        bounds2 = Bounds(*bounds2)

    if not bounds1.intersects(bounds2):
        return 0

    x_left = max(bounds1.x1, bounds2.x1)
    y_top = max(bounds1.y1, bounds2.y1)
    x_right = min(bounds1.x2, bounds2.x2)
    y_bottom = min(bounds1.y2, bounds2.y2)

    return (x_right - x_left) * (y_bottom - y_top)


def calculate_iou(
    bounds1: Bounds | tuple[int, int, int, int],
    bounds2: Bounds | tuple[int, int, int, int],
) -> float:
    """
    Calculate Intersection over Union (IoU) of two bounds.

    Args:
        bounds1: First bounds
        bounds2: Second bounds

    Returns:
        IoU value between 0.0 and 1.0
    """
    if isinstance(bounds1, tuple):
        bounds1 = Bounds(*bounds1)
    if isinstance(bounds2, tuple):
        bounds2 = Bounds(*bounds2)

    intersection_area = calculate_intersection_area(bounds1, bounds2)

    if intersection_area == 0:
        return 0.0

    union_area = bounds1.area + bounds2.area - intersection_area
    return intersection_area / union_area if union_area > 0 else 0.0


def describe_position(norm_x: float, norm_y: float) -> str:
    """
    Convert normalized coordinates (0.0-1.0) to semantic description.

    Args:
        norm_x: Normalized X coordinate (0.0 = left, 1.0 = right)
        norm_y: Normalized Y coordinate (0.0 = top, 1.0 = bottom)

    Returns:
        Semantic position description like "top-left", "center", "bottom-right"
    """
    # Horizontal segments
    if norm_x < 0.2:
        h = "left"
    elif norm_x < 0.4:
        h = "left-center"
    elif norm_x < 0.6:
        h = "center"
    elif norm_x < 0.8:
        h = "right-center"
    else:
        h = "right"

    # Vertical segments
    if norm_y < 0.2:
        v = "top"
    elif norm_y < 0.4:
        v = "upper"
    elif norm_y < 0.6:
        v = "middle"
    elif norm_y < 0.8:
        v = "lower"
    else:
        v = "bottom"

    return f"{v}-{h}"


def clamp_coordinates(x: int, y: int, max_x: int, max_y: int, min_x: int = 0, min_y: int = 0) -> tuple[int, int]:
    """
    Clamp coordinates to be within screen bounds.

    Args:
        x: X coordinate
        y: Y coordinate
        max_x: Maximum X value
        max_y: Maximum Y value
        min_x: Minimum X value (default 0)
        min_y: Minimum Y value (default 0)

    Returns:
        Clamped (x, y) coordinates
    """
    return max(min_x, min(x, max_x)), max(min_y, min(y, max_y))
