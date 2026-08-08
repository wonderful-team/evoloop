"""Schemas for environment module."""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class DehydratedElement(DynamicBaseModel):
    """A dehydrated Android UI element."""

    id: int
    text: str
    x: int
    y: int
    width: int
    height: int
    clickable: bool
    scrollable: bool = False
    package: str = ""
    class_: str = ""  # mapped from "class"
    resource_id: str = ""


class AndroidEvent(DynamicBaseModel):
    """Represents a single Android input event."""

    timestamp: float
    event_type: str  # "touch_down", "touch_up", "touch_move", "swipe", "key"
    x: int | None = None
    y: int | None = None
    key_code: int | None = None
    device_id: str = ""
    app_package: str | None = None
    swipe_end_x: int | None = None
    swipe_end_y: int | None = None
    swipe_duration_ms: float | None = None


class DebounceConfig(DynamicBaseModel):
    """Configuration for event debouncing."""

    # Time threshold in milliseconds - ignore events within this window
    time_threshold_ms: float = 50.0
    # Spatial threshold in pixels - ignore movements smaller than this
    spatial_threshold_px: int = 10
    # Maximum swipe events to keep (for very long swipes)
    max_swipe_points: int = 5


class AndroidTraceEvent(DynamicBaseModel):
    """Trace event representation for Android mirror sessions."""

    timestamp: int
    event_type: str
    target_selector: str | None = None
    target_text: str | None = None
    payload: dict = {}


class ElementResolutionResult(DynamicBaseModel):
    type: str | None = None
    value: str | None = None
    x: int | None = None
    y: int | None = None
    strategy: str | None = None
    parameters: dict | None = None
    source: str | None = None


class MirrorSessionStopResult(DynamicBaseModel):
    video_path: str | None = None
    events: list[AndroidTraceEvent] = Field(default_factory=list)
    session_id: str


class AppInfo(DynamicBaseModel):
    """Android (ADB) current-app model used by the **mobile controller**.

    Use this only for Android/mobile device current-app handling (see
    ``app.core.environment.controllers.mobile``). For a platform-agnostic
    current-app contract consumed by application-layer modules, prefer
    :class:`CurrentApp` via ``app.core.environment.get_current_app_context``.
    """

    package: str
    activity: str = ""
    confidence: float = 1.0


class CurrentApp(DynamicBaseModel):
    """Typed contract for the frontmost application, platform-agnostic.

    This is the canonical current-app outlet for application-layer consumers
    (engine / vision / tools / routing), obtained via
    ``app.core.environment.get_current_app_context``.

    - macOS populates ``name``/``pid``/``bounds``/``bundle_id``/``title``
    - Android (ADB) populates ``package``/``activity``

    Do NOT use :class:`AppInfo` for cross-platform code — it is Android-only.
    """

    name: str = "unknown"
    pid: int = -1
    bounds: str = "0,0,0,0"
    bundle_id: str | None = None
    title: str | None = None
    package: str | None = None
    activity: str | None = None
    platform: str = "unknown"


class BatchStepResult(DynamicBaseModel):
    step: int
    action: str
    status: str
    result: Any = None
    latency_ms: int


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


class HostEnvironment(DynamicBaseModel):
    """Host environment information (MacOS, Linux, Windows)."""

    os_name: str = "macOS"  # Default to macOS for backward compatibility
    os_version: str
    model: str
    cpu: str
    ram_gb: int
    installed_apps: list[str] = []
    # usage statistics keyed by app (populated by UsageRanker)
    app_usage_stats: list[AppUsageRecord] = Field(default_factory=list)
    # Linux-specific fields (dynamically probed)
    distro: str = "Linux"
    sudo_available: bool = False
    disk_space: str | None = None
    systemd_services: list[str] = Field(default_factory=list)
    gpus: list[str] = Field(default_factory=list)


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


class NetworkStatus(DynamicBaseModel):
    """Network connectivity status."""

    internet_connected: bool = False
    local_ips: list[str] = []


class LanDevice(DynamicBaseModel):
    """A device discovered on the local network via mDNS/DNS-SD + ARP."""

    ip: str
    mac: str = ""
    name: str = ""
    device_type: str = "unknown"
    manufacturer: str = ""
    model: str = ""
    services: list[str] = Field(default_factory=list)
    port: int | None = None


class BluetoothDevice(DynamicBaseModel):
    """A paired/connected Bluetooth device discovered on macOS."""

    name: str = ""
    address: str = ""
    device_type: str = "unknown"
    vendor: str = ""
    product_id: str = ""


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
    host: bool = False
    active_window: dict | None = None
    network: bool = False
    cpu: dict = Field(default_factory=dict)
    memory: dict = Field(default_factory=dict)
    context_usage_percent: int = 0


class PreferenceContext(DynamicBaseModel):
    """User preferences."""

    preferences: dict[str, str] = {}
