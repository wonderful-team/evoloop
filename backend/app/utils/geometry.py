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
