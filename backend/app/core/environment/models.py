"""
Awakening System Models - Core data structures for Agent environment awareness.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import Field, PrivateAttr

from app.infrastructure.pydantic_base import DynamicBaseModel

if TYPE_CHECKING:
    pass


class AppUsageRecord(DynamicBaseModel):
    """
    Activity profile for a single application.
    Produced by UsageRanker and stored in MacOSEnvironment.app_usage_stats.
    """
    app_name: str
    bundle_id: str
    platform: str = "macos"                   # "macos" | "android"
    last_used_at: datetime | None = None       # Last foreground activity
    total_foreground_ms: int = 0               # Cumulative foreground time (ms)
    priority_score: float = 0.0               # Normalized 0-1 combined score
    is_running: bool = False                   # Is the app currently running?


class MacOSEnvironment(DynamicBaseModel):
    """MacOS host environment information."""
    os_version: str
    model: str
    cpu: str
    ram_gb: int
    installed_apps: list[str] = []
    # usage statistics keyed by app (populated by UsageRanker)
    app_usage_stats: list[AppUsageRecord] = Field(default_factory=list)


class AndroidDevice(DynamicBaseModel):
    """Connected Android device information."""
    device_id: str
    model: str
    os_version: str
    sdk_version: int
    battery_percent: int
    installed_packages: list[str] = []
    is_reachable: bool = True
    # usage statistics keyed by app (populated by UsageRanker)
    app_usage_stats: list[AppUsageRecord] = Field(default_factory=list)

    @property
    def serial(self) -> str:
        """Alias for device_id (compatibility with ADB terminology)."""
        return self.device_id


class NetworkStatus(DynamicBaseModel):
    """Network connectivity status."""
    internet_connected: bool = False
    local_ips: list[str] = []


class EpisodeSummary(DynamicBaseModel):
    """Summary of a past task execution."""
    date: str
    goal: str
    result: str  # SUCCESS, PARTIAL, FAILED


class ConceptSummary(DynamicBaseModel):
    """Summary of a knowledge concept."""
    name: str
    description: str = ""


class MemoryContext(DynamicBaseModel):
    """Aggregated memory context for awakening."""
    episodes: list[EpisodeSummary] = []
    concepts: list[ConceptSummary] = []
    journal_highlights: str = ""


class AndroidTelemetry(DynamicBaseModel):
    id: str
    reachable: bool


class TelemetrySnapshot(DynamicBaseModel):
    android: list[AndroidTelemetry] = Field(default_factory=list)
    macos: bool = False
    network: bool = False


class PreferenceContext(DynamicBaseModel):
    """User preferences."""
    preferences: dict[str, str] = {}


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
