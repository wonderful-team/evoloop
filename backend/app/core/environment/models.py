"""
Awakening System Models - Core data structures for Agent environment awareness.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import PrivateAttr

from app.core.environment.schemas import HostEnvironment, AndroidDevice, NetworkStatus, EpisodeSummary, ConceptSummary, \
    AndroidTelemetry, TelemetrySnapshot
from app.infrastructure.pydantic_base import DynamicBaseModel

if TYPE_CHECKING:
    pass


class AwakenedState(DynamicBaseModel):
    """
    Complete awakened state of the Agent.
    Represents what the Agent "knows" about itself and its environment.
    """
    # == Environment Layer ==
    timestamp: datetime
    host: HostEnvironment | None = None
    android_devices: list[AndroidDevice] = []
    network: NetworkStatus = NetworkStatus()
    docker_containers: list[dict] = []

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
        if self.host:
            platforms.append(self.host.os_name.lower())
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
        import psutil
        try:
            cpu_data = {"usage_percent": psutil.cpu_percent(interval=None), "load_avg": psutil.getloadavg() if hasattr(psutil, "getloadavg") else []}
            mem = psutil.virtual_memory()
            mem_data = {"percent": mem.percent, "available": mem.available}
        except Exception:
            cpu_data = {}
            mem_data = {}

        self._telemetry_cache = TelemetrySnapshot(
            android=[
                AndroidTelemetry(id=d.device_id, reachable=d.is_reachable)
                for d in self.android_devices
            ],
            host=bool(self.host),
            network=self.network.internet_connected if self.network else False,
            cpu=cpu_data,
            memory=mem_data,
            context_usage_percent=0  # Filled dynamically by context_hydrator later if possible
        )
        self._telemetry_cache_time = now
        return self._telemetry_cache
