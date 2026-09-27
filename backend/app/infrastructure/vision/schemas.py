"""Schemas for vision module."""

from app.infrastructure.pydantic_base import DynamicBaseModel


class CleanupResult(DynamicBaseModel):
    """Result of a single cleanup operation."""

    dry_run: bool
    total: int
    timestamp: str


class ScreenshotCleanupResult(CleanupResult):
    """Result of screenshot cleanup."""

    files_cleaned: dict[str, int]


class RecordingCleanupResult(CleanupResult):
    """Result of screen recording cleanup."""

    items_cleaned: dict[str, int]


class CombinedCleanupResult(DynamicBaseModel):
    """Combined result of screenshot and recording cleanup."""

    dry_run: bool
    screenshots: ScreenshotCleanupResult
    recordings: RecordingCleanupResult
    total_cleaned: int
    timestamp: str
