"""Atlas source event types — module-internal events for AppMap lifecycle."""

from enum import Enum


class AppMapEventType(str, Enum):
    CREATED = "atlas.app_map.created"
    SUPERSEDED = "atlas.app_map.superseded"
