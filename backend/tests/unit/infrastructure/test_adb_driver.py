"""
Unit tests for ADB driver.
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open

from app.infrastructure.drivers.adb import ADBDriver, ADBError


class TestADBDriverBasic:
    """Basic tests for ADBDriver."""

    def test_adb_driver_imports(self):
        """Test that ADB driver can be imported."""
        assert ADBDriver is not None
        assert ADBError is not None

    def test_adb_driver_methods_exist(self):
        """Test that ADB driver has expected methods."""
        assert hasattr(ADBDriver, 'list_devices')
        assert hasattr(ADBDriver, 'screenshot')
        assert hasattr(ADBDriver, 'tap')
        assert hasattr(ADBDriver, 'swipe')
        assert hasattr(ADBDriver, 'input_text')
        assert hasattr(ADBDriver, 'press_key')
        assert hasattr(ADBDriver, 'launch_app')
        assert hasattr(ADBDriver, 'dump_ui')
        assert hasattr(ADBDriver, 'get_screen_size')
        assert hasattr(ADBDriver, 'get_system_info')


class TestADBError:
    """Tests for ADBError exception."""

    def test_adb_error_raises(self):
        """Test that ADBError can be raised."""
        with pytest.raises(ADBError, match="Test error"):
            raise ADBError("Test error")


class TestADBDriverInit:
    """Tests for ADBDriver initialization."""

    @patch('os.path.exists')
    def test_find_adb_from_common_paths(self, mock_exists):
        """Test finding adb from common paths."""
        mock_exists.side_effect = lambda path: path == "/opt/homebrew/bin/adb"

        driver = ADBDriver()
        assert driver._adb_path == "/opt/homebrew/bin/adb"


class TestADBScreenshot:
    """Tests for screenshot functionality."""

    def test_screenshot_method_exists(self):
        """Test that screenshot method exists."""
        from app.infrastructure.drivers.adb import ADBDriver
        assert hasattr(ADBDriver, 'screenshot')


class TestADBGestures:
    """Tests for gesture operations."""

    @patch('app.infrastructure.drivers.adb.subprocess.run')
    @patch('os.path.exists')
    def test_tap(self, mock_exists, mock_run):
        """Test tap at coordinates."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        driver = ADBDriver()
        driver.tap(100, 200)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "tap" in args

    @patch('app.infrastructure.drivers.adb.subprocess.run')
    @patch('os.path.exists')
    def test_swipe(self, mock_exists, mock_run):
        """Test swipe gesture."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        driver = ADBDriver()
        driver.swipe(100, 200, 300, 400, duration_ms=500)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "swipe" in args


class TestADBInput:
    """Tests for text input."""

    def test_input_text_method_exists(self):
        """Test input_text method exists."""
        from app.infrastructure.drivers.adb import ADBDriver
        assert hasattr(ADBDriver, 'input_text')

    def test_press_key_method_exists(self):
        """Test press_key method exists."""
        from app.infrastructure.drivers.adb import ADBDriver
        assert hasattr(ADBDriver, 'press_key')

    @patch('app.infrastructure.drivers.adb.subprocess.run')
    @patch('os.path.exists')
    def test_press_key_executes(self, mock_exists, mock_run):
        """Test pressing key executes subprocess."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        driver = ADBDriver()
        driver.press_key("KEYCODE_ENTER")

        # Should call subprocess at least once
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "keyevent" in args


class TestADBAppLaunch:
    """Tests for app launching."""

    @patch('app.infrastructure.drivers.adb.subprocess.run')
    @patch('os.path.exists')
    def test_launch_app(self, mock_exists, mock_run):
        """Test launching app."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        driver = ADBDriver()
        driver.launch_app("com.example.app")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "monkey" in args
        assert "com.example.app" in args


class TestADBScreenInfo:
    """Tests for screen information."""

    @patch('app.infrastructure.drivers.adb.subprocess.run')
    @patch('os.path.exists')
    def test_get_screen_size(self, mock_exists, mock_run):
        """Test getting screen size."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Physical size: 1080x1920\n",
            stderr=""
        )

        driver = ADBDriver()
        width, height = driver.get_screen_size()

        assert width == 1080
        assert height == 1920


class TestADBDumpUI:
    """Tests for UI dumping."""

    def test_dump_ui_method_exists(self):
        """Test dump_ui method exists."""
        from app.infrastructure.drivers.adb import ADBDriver
        assert hasattr(ADBDriver, 'dump_ui')


class TestADBSystemInfo:
    """Tests for system information."""

    def test_get_system_info_method_exists(self):
        """Test get_system_info method exists."""
        from app.infrastructure.drivers.adb import ADBDriver
        assert hasattr(ADBDriver, 'get_system_info')

    def test_get_current_app_method_exists(self):
        """Test get_current_app method exists."""
        from app.infrastructure.drivers.adb import ADBDriver
        assert hasattr(ADBDriver, 'get_current_app')

    @patch('app.infrastructure.drivers.adb.subprocess.run')
    @patch('os.path.exists')
    def test_get_current_app_executes(self, mock_exists, mock_run):
        """Test getting current app executes subprocess."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="mFocusedApp=ActivityRecord{... com.example.app/.MainActivity}\n",
            stderr=""
        )

        driver = ADBDriver()
        app = driver.get_current_app()

        assert mock_run.called
