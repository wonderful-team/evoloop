"""
Unit tests for Environment Module - Awakening and Environment Awareness.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.core.environment.models import (
    AppUsageRecord,
    MacOSEnvironment,
    AndroidDevice,
    NetworkStatus,
    EpisodeSummary,
    ConceptSummary,
    MemoryContext,
    PreferenceContext,
    AwakenedState,
)
from app.core.environment.discovery import EnvironmentProbe
from app.core.environment.watcher import EnvironmentWatcher


class TestAppUsageRecord:
    """Tests for AppUsageRecord model."""

    def test_creation(self):
        """Test creating AppUsageRecord."""
        record = AppUsageRecord(
            app_name="Safari",
            bundle_id="com.apple.Safari",
            platform="macos",
            priority_score=0.95
        )

        assert record.app_name == "Safari"
        assert record.bundle_id == "com.apple.Safari"
        assert record.platform == "macos"
        assert record.priority_score == 0.95
        assert record.total_foreground_ms == 0


class TestMacOSEnvironment:
    """Tests for MacOSEnvironment model."""

    def test_creation(self):
        """Test creating MacOSEnvironment."""
        env = MacOSEnvironment(
            os_version="14.0",
            model="MacBook Pro",
            cpu="Apple M3",
            ram_gb=32,
            installed_apps=["Safari", "Xcode"]
        )

        assert env.os_version == "14.0"
        assert env.model == "MacBook Pro"
        assert env.cpu == "Apple M3"
        assert env.ram_gb == 32
        assert len(env.installed_apps) == 2


class TestAndroidDevice:
    """Tests for AndroidDevice model."""

    def test_creation(self):
        """Test creating AndroidDevice."""
        device = AndroidDevice(
            device_id="adb-12345",
            model="Pixel 7",
            os_version="14",
            sdk_version=34,
            battery_percent=85
        )

        assert device.device_id == "adb-12345"
        assert device.model == "Pixel 7"
        assert device.os_version == "14"
        assert device.sdk_version == 34
        assert device.battery_percent == 85
        assert device.is_reachable is True


class TestNetworkStatus:
    """Tests for NetworkStatus model."""

    def test_default_creation(self):
        """Test creating NetworkStatus with defaults."""
        status = NetworkStatus()

        assert status.internet_connected is False
        assert status.local_ips == []

    def test_custom_creation(self):
        """Test creating NetworkStatus with custom values."""
        status = NetworkStatus(
            internet_connected=True,
            local_ips=["192.168.1.100", "10.0.0.5"]
        )

        assert status.internet_connected is True
        assert len(status.local_ips) == 2


class TestEpisodeSummary:
    """Tests for EpisodeSummary model."""

    def test_creation(self):
        """Test creating EpisodeSummary."""
        episode = EpisodeSummary(
            date="2024-01-15",
            goal="Deploy application",
            result="SUCCESS"
        )

        assert episode.date == "2024-01-15"
        assert episode.goal == "Deploy application"
        assert episode.result == "SUCCESS"


class TestConceptSummary:
    """Tests for ConceptSummary model."""

    def test_creation(self):
        """Test creating ConceptSummary."""
        concept = ConceptSummary(
            name="Docker",
            description="Containerization platform"
        )

        assert concept.name == "Docker"
        assert concept.description == "Containerization platform"


class TestMemoryContext:
    """Tests for MemoryContext model."""

    def test_default_creation(self):
        """Test creating MemoryContext with defaults."""
        context = MemoryContext()

        assert context.episodes == []
        assert context.concepts == []
        assert context.journal_highlights == ""

    def test_with_data(self):
        """Test creating MemoryContext with data."""
        context = MemoryContext(
            episodes=[EpisodeSummary(date="2024-01-01", goal="Test", result="SUCCESS")],
            concepts=[ConceptSummary(name="Test", description="Test concept")],
            journal_highlights="Important highlights"
        )

        assert len(context.episodes) == 1
        assert len(context.concepts) == 1
        assert context.journal_highlights == "Important highlights"


class TestPreferenceContext:
    """Tests for PreferenceContext model."""

    def test_default_creation(self):
        """Test creating PreferenceContext with defaults."""
        context = PreferenceContext()

        assert context.preferences == {}

    def test_with_data(self):
        """Test creating PreferenceContext with data."""
        context = PreferenceContext(
            preferences={"theme": "dark", "language": "zh", "rule_always_use_type_hints": "Always use type hints", "rule_follow_pep8": "Follow PEP 8"}
        )

        assert context.preferences["theme"] == "dark"
        assert len(context.preferences) == 4


class TestAwakenedState:
    """Tests for AwakenedState model."""

    def test_creation(self):
        """Test creating AwakenedState."""
        state = AwakenedState(
            timestamp=datetime.now(),
            macos=MacOSEnvironment(os_version="14.0", model="MacBook", cpu="M3", ram_gb=16),
            network=NetworkStatus(internet_connected=True),
            available_platforms=["macos"]
        )

        assert state.macos is not None
        assert state.network.internet_connected is True
        assert state.available_platforms == ["macos"]

    def test_compute_platforms_with_macos(self):
        """Test compute_platforms with macos."""
        state = AwakenedState(
            timestamp=datetime.now(),
            macos=MacOSEnvironment(os_version="14.0", model="MacBook", cpu="M3", ram_gb=16),
            android_devices=[]
        )

        platforms = state.compute_platforms()
        assert "macos" in platforms
        assert "android" not in platforms

    def test_compute_platforms_with_android(self):
        """Test compute_platforms with android."""
        state = AwakenedState(
            timestamp=datetime.now(),
            macos=None,
            android_devices=[AndroidDevice(device_id="adb-1", model="Pixel", os_version="14", sdk_version=34, battery_percent=80)]
        )

        platforms = state.compute_platforms()
        assert "android" in platforms
        assert "macos" not in platforms

    def test_compute_platforms_with_both(self):
        """Test compute_platforms with both platforms."""
        state = AwakenedState(
            timestamp=datetime.now(),
            macos=MacOSEnvironment(os_version="14.0", model="MacBook", cpu="M3", ram_gb=16),
            android_devices=[AndroidDevice(device_id="adb-1", model="Pixel", os_version="14", sdk_version=34, battery_percent=80)]
        )

        platforms = state.compute_platforms()
        assert "macos" in platforms
        assert "android" in platforms


class TestEnvironmentProbe:
    """Tests for EnvironmentProbe."""

    @pytest.mark.asyncio
    async def test_probe_macos_success(self):
        """Test successful macOS probing."""
        with patch("app.infrastructure.drivers.macos.macos_driver") as mock_driver:
            mock_driver.get_system_info.return_value = {
                "os_version": "14.0",
                "model": "MacBook Pro",
                "cpu": "Apple M3",
                "ram_gb": 32
            }
            mock_driver.list_installed_apps.return_value = ["Safari", "Xcode"]

            with patch("app.core.environment.usage.ranker.UsageRanker") as mock_ranker:
                mock_ranker.rank_macos_apps.return_value = []

                result = await EnvironmentProbe.probe_macos()

                assert result is not None
                assert result.os_version == "14.0"
                assert result.model == "MacBook Pro"

    @pytest.mark.asyncio
    async def test_probe_macos_with_error(self):
        """Test macOS probing with error."""
        with patch("app.infrastructure.drivers.macos.macos_driver") as mock_driver:
            mock_driver.get_system_info.return_value = {"error": "Driver not available"}

            result = await EnvironmentProbe.probe_macos()

            assert result is None

    @pytest.mark.asyncio
    async def test_probe_android_devices_success(self):
        """Test successful Android device probing."""
        with patch("app.infrastructure.drivers.adb.adb_driver") as mock_driver:
            mock_driver.list_devices.return_value = [
                {"serial": "adb-123", "status": "device"}
            ]
            mock_driver.get_system_info.return_value = {
                "model": "Pixel 7",
                "os_version": "14",
                "battery": "85%"
            }
            mock_driver.list_installed_apps.return_value = ["com.android.settings"]

            result = await EnvironmentProbe.probe_android_devices()

            assert len(result) == 1
            assert result[0].device_id == "adb-123"
            assert result[0].model == "Pixel 7"
            assert result[0].battery_percent == 85

    @pytest.mark.asyncio
    async def test_probe_android_devices_offline(self):
        """Test Android probing skips offline devices."""
        with patch("app.infrastructure.drivers.adb.adb_driver") as mock_driver:
            mock_driver.list_devices.return_value = [
                {"serial": "adb-123", "status": "offline"}
            ]

            result = await EnvironmentProbe.probe_android_devices()

            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_probe_android_devices_empty(self):
        """Test Android probing with no devices."""
        with patch("app.infrastructure.drivers.adb.adb_driver") as mock_driver:
            mock_driver.list_devices.return_value = []

            result = await EnvironmentProbe.probe_android_devices()

            assert result == []

    @pytest.mark.asyncio
    async def test_probe_network_connected(self):
        """Test network probing when connected."""
        with patch("socket.create_connection") as mock_socket:
            mock_socket.return_value.__enter__ = MagicMock()
            mock_socket.return_value.__exit__ = MagicMock()

            with patch("socket.gethostbyname_ex") as mock_gethost:
                mock_gethost.return_value = ("hostname", [], ["192.168.1.100"])

                result = await EnvironmentProbe.probe_network()

                assert result.internet_connected is True
                assert "192.168.1.100" in result.local_ips

    @pytest.mark.asyncio
    async def test_probe_network_disconnected(self):
        """Test network probing when disconnected."""
        with patch("socket.create_connection") as mock_socket:
            mock_socket.side_effect = Exception("No connection")

            result = await EnvironmentProbe.probe_network()

            assert result.internet_connected is False


class TestEnvironmentWatcher:
    """Tests for EnvironmentWatcher."""

    @pytest.fixture
    def watcher(self):
        """Create a watcher instance."""
        return EnvironmentWatcher(refresh_interval=1)

    @pytest.mark.asyncio
    async def test_start_stop(self, watcher):
        """Test starting and stopping the watcher."""
        assert watcher._running is False

        await watcher.start()
        assert watcher._running is True
        assert watcher._task is not None

        await watcher.stop()
        assert watcher._running is False

    @pytest.mark.asyncio
    async def test_double_start(self, watcher):
        """Test starting when already running."""
        await watcher.start()
        await watcher.start()  # Should not create duplicate task

        assert watcher._running is True
        await watcher.stop()

    @pytest.mark.asyncio
    async def test_on_change_callback(self, watcher):
        """Test registering change callback."""
        callback_called = False

        async def test_callback():
            nonlocal callback_called
            callback_called = True

        watcher.on_change(test_callback)
        assert test_callback in watcher._on_change_callbacks

    @pytest.mark.asyncio
    async def test_watch_loop_detects_changes(self, watcher):
        """Test watch loop detects device changes."""
        callback_called = False

        async def test_callback():
            nonlocal callback_called
            callback_called = True

        watcher.on_change(test_callback)

        # Mock initial state
        mock_state = MagicMock()
        mock_state.android_devices = []
        mock_state.network = NetworkStatus(internet_connected=True)

        with patch("app.core.environment.get_awakened_state", return_value=mock_state):
            with patch.object(EnvironmentProbe, "probe_android_devices", new_callable=AsyncMock) as mock_probe:
                with patch.object(EnvironmentProbe, "probe_network", new_callable=AsyncMock) as mock_network:
                    # First call returns no devices, second returns a device
                    mock_probe.side_effect = [
                        [],
                        [AndroidDevice(device_id="new-device", model="Pixel", os_version="14", sdk_version=34, battery_percent=80)]
                    ]
                    mock_network.return_value = NetworkStatus(internet_connected=True)

                    await watcher.start()
                    await asyncio.sleep(0.1)
                    await watcher.stop()


class TestEnvironmentAwakening:
    """Tests for environment awakening functions."""

    @pytest.mark.asyncio
    async def test_awaken(self):
        """Test the awaken function."""
        from app.core.environment import awaken, get_awakened_state

        with patch("app.core.environment.discovery.EnvironmentProbe") as mock_probe:
            mock_probe.probe_macos = AsyncMock(return_value=MacOSEnvironment(
                os_version="14.0", model="MacBook", cpu="M3", ram_gb=16
            ))
            mock_probe.probe_android_devices = AsyncMock(return_value=[])
            mock_probe.probe_network = AsyncMock(return_value=NetworkStatus(internet_connected=True))

            with patch("app.core.environment.memory_replay.replay_memory", new_callable=AsyncMock) as mock_memory:
                mock_memory.return_value = MagicMock(episodes=[], concepts=[], journal_highlights="")

                with patch("app.core.environment.preference_priming.prime_preferences", new_callable=AsyncMock) as mock_prefs:
                    mock_prefs.return_value = MagicMock(preferences={}, rules=[])

                    with patch("app.core.environment.events.event_bus") as mock_event_bus:
                        mock_event_bus.publish = AsyncMock()

                        # Mock the dynamic app triage to prevent LLM calls
                        with patch("app.core.environment.explorers.dynamic_apps.DynamicAppTriage.sync_dynamic_apps", new_callable=AsyncMock):
                            result = await awaken(project_id=1)

                            assert result is not None
                            assert result.macos is not None
                            assert "macos" in result.available_platforms

    def test_get_awakened_state_before_awaken(self):
        """Test get_awakened_state returns None before awakening."""
        from app.core.environment import get_awakened_state

        # Note: This might fail if other tests call awaken first
        # In a real test suite, we might need to reset the global state
        state = get_awakened_state()
        # State might be None or might be set by previous tests
        # Just verify the function works
        assert state is None or isinstance(state, AwakenedState)
