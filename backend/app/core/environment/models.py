"""
Awakening System Models - Core data structures for Agent environment awareness.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import Field, PrivateAttr

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.environment.schemas import AppUsageRecord, MacOSEnvironment, AndroidDevice, NetworkStatus, EpisodeSummary, ConceptSummary, MemoryContext, AndroidTelemetry, TelemetrySnapshot, PreferenceContext

if TYPE_CHECKING:
    pass


class AwakenedState(DynamicBaseModel):
    """
    Complete awakened state of the Agent.
    Represents what the Agent "knows" about itself and its environment.
    """
    # == Environment Layer ==
    timestamp: datetime
    macos: MacOSEnvironment | None = None
    android_devices: list[AndroidDevice] = []
    network: NetworkStatus = NetworkStatus()

    # == Memory Layer ==
    recent_episodes: list[EpisodeSummary] = []
    relevant_concepts: list[ConceptSummary] = []
    journal_highlights: str = ""

    # == Preference Layer ==
    user_preferences: dict[str, str] = {}

    # == Capability Boundaries ==
    available_platforms: list[str] = []
    capability_boundaries: list[str] = []

    # == Telemetry Cache (Private) ==
    _telemetry_cache: dict | None = PrivateAttr(default=None)
    _telemetry_cache_time: float = PrivateAttr(default=0.0)
    _telemetry_cache_ttl: float = PrivateAttr(default=0.5)  # 500ms TTL (保守策略)

    def compute_platforms(self) -> list[str]:
        """Compute available platforms based on environment."""
        platforms = []
        if self.macos:
            platforms.append("macos")
        if self.android_devices:
            platforms.append("android")
        return platforms

    def get_telemetry_snapshot(self) -> TelemetrySnapshot:
        """
        Get telemetry snapshot with caching.
        
        Returns a lightweight dict with device connectivity status.
        Uses 1-second TTL cache to avoid redundant computation.
        
        Returns:
            dict with keys: "android", "macos", "network"
        """
        now = time.time()

        # Return cached value if still valid
        if (self._telemetry_cache is not None and now - self._telemetry_cache_time) < self._telemetry_cache_ttl:
            return self._telemetry_cache

        # Compute fresh snapshot
        self._telemetry_cache = TelemetrySnapshot(
            android=[
                AndroidTelemetry(id=d.device_id, reachable=d.is_reachable)
                for d in self.android_devices
            ],
            macos=bool(self.macos),
            network=self.network.internet_connected if self.network else False
        )
        self._telemetry_cache_time = now
        return self._telemetry_cache
