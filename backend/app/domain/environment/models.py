"""
Awakening System Models - Core data structures for Agent environment awareness.
"""

from datetime import datetime
from pydantic import BaseModel


class MacOSEnvironment(BaseModel):
    """MacOS host environment information."""
    os_version: str
    model: str
    cpu: str
    ram_gb: int
    installed_apps: list[str] = []


class AndroidDevice(BaseModel):
    """Connected Android device information."""
    device_id: str
    model: str
    os_version: str
    sdk_version: int
    battery_percent: int
    installed_packages: list[str] = []
    is_reachable: bool = True


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
    """User preferences and system rules."""
    preferences: dict[str, str] = {}
    rules: list[str] = []


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
    system_rules: list[str] = []
    
    # == Capability Boundaries ==
    available_platforms: list[str] = []
    capability_boundaries: list[str] = []
    
    # == Discovery Layer (Active Awakening) ==
    discovery_report: dict = {} # Platform specific discovery results
    
    def compute_platforms(self) -> list[str]:
        """Compute available platforms based on environment."""
        platforms = []
        if self.macos:
            platforms.append("macos")
        if self.android_devices:
            platforms.append("android")
        return platforms
