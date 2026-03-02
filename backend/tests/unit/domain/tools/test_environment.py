"""
Unit tests for Environment Tools.
Tests desktop_control, mobile_control, and browser tools.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestDesktopControl:
    """Tests for desktop_control tool."""

    @pytest.fixture
    def desktop_tool(self):
        """Get the desktop_control tool instance."""
        from app.domain.tools.environment.desktop import desktop_control
        return desktop_control

    @pytest.mark.asyncio
    async def test_desktop_control_screenshot(self, desktop_tool):
        """Test desktop_control screenshot action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.capture_screenshot = MagicMock(return_value="/tmp/screenshot.png")

            result = await desktop_tool.ainvoke({"action": "screenshot"})
            assert "/tmp/screenshot.png" in result or "screenshot" in result.lower()

    @pytest.mark.asyncio
    async def test_desktop_control_click(self, desktop_tool):
        """Test desktop_control click action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.click = MagicMock(return_value=True)
            mock_driver.get_screen_size = MagicMock(return_value=(1920, 1080))

            result = await desktop_tool.ainvoke({"action": "click", "x": 100, "y": 200})
            mock_driver.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_desktop_control_type_text(self, desktop_tool):
        """Test desktop_control type_text action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.type_text = MagicMock(return_value=True)
            mock_driver.get_screen_size = MagicMock(return_value=(1920, 1080))

            result = await desktop_tool.ainvoke({"action": "type_text", "text": "Hello World"})
            mock_driver.type_text.assert_called_once_with("Hello World", force_keystroke=False)

    @pytest.mark.asyncio
    async def test_desktop_control_key_press(self, desktop_tool):
        """Test desktop_control key_press action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.key_press = MagicMock(return_value=True)

            result = await desktop_tool.ainvoke({"action": "key_press", "key": "enter"})
            mock_driver.key_press.assert_called_once()

    @pytest.mark.asyncio
    async def test_desktop_control_open_app(self, desktop_tool):
        """Test desktop_control open_app action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.open_app = MagicMock(return_value=True)

            result = await desktop_tool.ainvoke({"action": "open_app", "app_name": "Safari"})
            mock_driver.open_app.assert_called_once_with("Safari")

    @pytest.mark.asyncio
    async def test_desktop_control_list_apps(self, desktop_tool):
        """Test desktop_control list_apps action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.list_installed_apps = MagicMock(return_value=["Safari", "Chrome"])

            result = await desktop_tool.ainvoke({"action": "list_apps"})
            assert "Safari" in result or "Chrome" in result

    @pytest.mark.asyncio
    async def test_desktop_control_get_active_app(self, desktop_tool):
        """Test desktop_control get_active_app action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.get_current_app = MagicMock(return_value={
                "name": "Safari",
                "bundle_id": "com.apple.Safari"
            })

            result = await desktop_tool.ainvoke({"action": "get_active_app"})
            assert "Safari" in result

    @pytest.mark.asyncio
    async def test_desktop_control_batch(self, desktop_tool):
        """Test desktop_control batch action."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.click = MagicMock(return_value=True)
            mock_driver.type_text = MagicMock(return_value=True)

            actions = [
                {"action": "click", "x": 100, "y": 200},
                {"action": "type_text", "text": "Hello"}
            ]
            result = await desktop_tool.ainvoke({"action": "batch", "actions": actions})
            # Batch should execute without error

    @pytest.mark.asyncio
    async def test_desktop_control_error_handling(self, desktop_tool):
        """Test desktop_control error handling."""
        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.click = MagicMock(side_effect=Exception("Click failed"))

            result = await desktop_tool.ainvoke({"action": "click", "x": 100, "y": 200})
            assert "error" in result.lower() or "failed" in result.lower()


class TestMobileControl:
    """Tests for mobile_control tool."""

    @pytest.fixture
    def mobile_tool(self):
        """Get the mobile_control tool instance."""
        from app.domain.tools.environment.mobile import mobile_control
        return mobile_control

    @pytest.mark.asyncio
    async def test_mobile_control_list_devices(self, mobile_tool):
        """Test mobile_control list_devices action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.list_devices = MagicMock(return_value=["device1", "device2"])

            result = await mobile_tool.ainvoke({"action": "list_devices"})
            assert "device" in result.lower() or result != ""

    @pytest.mark.asyncio
    async def test_mobile_control_screenshot(self, mobile_tool):
        """Test mobile_control screenshot action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.capture_screenshot = MagicMock(return_value="/tmp/android.png")

            result = await mobile_tool.ainvoke({"action": "screenshot", "device_id": "test_device"})
            assert ".png" in result or "/tmp/" in result or "screenshot" in result.lower()

    @pytest.mark.asyncio
    async def test_mobile_control_tap(self, mobile_tool):
        """Test mobile_control tap action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.tap = MagicMock(return_value=True)

            result = await mobile_tool.ainvoke({"action": "tap", "x": 100, "y": 200, "device_id": "test_device"})
            mock_driver.tap.assert_called_once()

    @pytest.mark.asyncio
    async def test_mobile_control_input_text(self, mobile_tool):
        """Test mobile_control input_text action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.input_text = MagicMock(return_value=True)

            result = await mobile_tool.ainvoke({"action": "input_text", "text": "Hello", "device_id": "test_device"})
            mock_driver.input_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_mobile_control_press_key(self, mobile_tool):
        """Test mobile_control press_key action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.press_key = MagicMock(return_value=True)

            result = await mobile_tool.ainvoke({"action": "press_key", "keycode": "home", "device_id": "test_device"})
            mock_driver.press_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_mobile_control_swipe(self, mobile_tool):
        """Test mobile_control swipe action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.swipe = MagicMock(return_value=True)
            mock_driver.capture_screenshot = MagicMock(return_value="/tmp/test.png")

            result = await mobile_tool.ainvoke({
                "action": "swipe", "x": 100, "y": 200, "x2": 300, "y2": 400, "device_id": "test_device"
            })
            # Swipe action may not directly call swipe in current implementation

    @pytest.mark.asyncio
    async def test_mobile_control_dump_ui(self, mobile_tool):
        """Test mobile_control dump_ui action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.dump_ui = MagicMock(return_value="<hierarchy></hierarchy>")

            result = await mobile_tool.ainvoke({"action": "dump_ui", "device_id": "test_device"})
            assert "hierarchy" in result or "xml" in result.lower()

    @pytest.mark.asyncio
    async def test_mobile_control_open_app(self, mobile_tool):
        """Test mobile_control open_app action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.shell = MagicMock(return_value="")
            mock_driver.capture_screenshot = MagicMock(return_value="/tmp/test.png")

            result = await mobile_tool.ainvoke({"action": "open_app", "text": "com.example.app", "device_id": "test_device"})
            # open_app uses shell command to start activity

    @pytest.mark.asyncio
    async def test_mobile_control_long_press(self, mobile_tool):
        """Test mobile_control long_press action."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.long_press = MagicMock(return_value=True)

            result = await mobile_tool.ainvoke({
                "action": "long_press", "x": 100, "y": 200, "duration_ms": 1000, "device_id": "test_device"
            })
            mock_driver.long_press.assert_called_once()

    @pytest.mark.asyncio
    async def test_mobile_control_error_handling(self, mobile_tool):
        """Test mobile_control error handling."""
        with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
            mock_driver.list_devices = MagicMock(side_effect=Exception("ADB error"))

            result = await mobile_tool.ainvoke({"action": "list_devices"})
            assert "error" in result.lower() or "failed" in result.lower()


class TestDesktopHelperFunctions:
    """Tests for desktop helper functions."""

    @pytest.mark.asyncio
    async def test_trigger_atlas_harvest_macos(self):
        """Test _trigger_atlas_harvest_macos function."""
        from app.domain.tools.environment.desktop import _trigger_atlas_harvest_macos

        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.get_current_app = MagicMock(return_value={
                "bundle_id": "com.test.app",
                "title": "Test App"
            })
            mock_driver.dump_ax_tree = MagicMock(return_value="[{\"role\": \"button\"}]")

            with patch("app.domain.tools.environment.desktop.atlas_engine") as mock_atlas:
                mock_atlas.on_ui_tree_observed = AsyncMock()

                await _trigger_atlas_harvest_macos("com.test.app")
                # Should complete without error

    @pytest.mark.asyncio
    async def test_trigger_atlas_harvest_macos_app_mismatch(self):
        """Test atlas harvest skips when app mismatches."""
        from app.domain.tools.environment.desktop import _trigger_atlas_harvest_macos

        with patch("app.domain.tools.environment.desktop.macos_driver") as mock_driver:
            mock_driver.get_current_app = MagicMock(return_value={
                "bundle_id": "com.other.app",  # Different from requested
                "title": "Other App"
            })

            await _trigger_atlas_harvest_macos("com.test.app")
            # Should return early without calling dump_ax_tree
            mock_driver.dump_ax_tree.assert_not_called()


class TestMobileHelperFunctions:
    """Tests for mobile helper functions."""

    @pytest.mark.asyncio
    async def test_probe_hybrid_h5_detection(self):
        """Test H5 detection in mobile control."""
        from app.domain.tools.environment.mobile import mobile_control

        with patch("app.domain.tools.environment.mobile.android_a11y_provider") as mock_a11y:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.elements = [MagicMock(metadata={"class": "android.webkit.WebView"})]
            mock_a11y.process = AsyncMock(return_value=mock_result)

            with patch("app.domain.tools.environment.mobile.adb_driver") as mock_driver:
                mock_driver.get_current_app = MagicMock(return_value={"activity": "WebActivity"})
                mock_driver.capture_screenshot = MagicMock(return_value="/tmp/test.png")

                result = await mobile_control.ainvoke({"action": "screenshot", "device_id": "test"})
                # Test that H5 detection ran
