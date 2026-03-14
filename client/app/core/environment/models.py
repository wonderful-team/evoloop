"""
Awakening System Models - Core data structures for Agent environment awareness.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


class AppUsageRecord(BaseModel):
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


class MacOSEnvironment(BaseModel):
    """MacOS host environment information."""
    os_version: str
    model: str
    cpu: str
    ram_gb: int
    installed_apps: list[str] = []
    # usage statistics keyed by app (populated by UsageRanker)
    app_usage_stats: list[AppUsageRecord] = Field(default_factory=list)


class AndroidDevice(BaseModel):
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


class NetworkStatus(BaseModel):
    """Network connectivity status."""
    internet_connected: bool = False
    local_ips: list[str] = []


class EpisodeSummary(BaseModel):
    """Summary of a past task execution."""
    date: str
    goal: str
    result: str  # SUCCESS, PARTIAL, FAILED


class ConceptSummary(BaseModel):
    """Summary of a knowledge concept."""
    name: str
    description: str = ""


class MemoryContext(BaseModel):
    """Aggregated memory context for awakening."""
    episodes: list[EpisodeSummary] = []
    concepts: list[ConceptSummary] = []
    journal_highlights: str = ""


class PreferenceContext(BaseModel):
    """User preferences."""
    preferences: dict[str, str] = {}


class AwakenedState(BaseModel):
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

    def compute_platforms(self) -> list[str]:
        """Compute available platforms based on environment."""
        platforms = []
        if self.macos:
            platforms.append("macos")
        if self.android_devices:
            platforms.append("android")
        return platforms
