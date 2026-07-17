import os
from unittest.mock import patch, MagicMock, mock_open
from app.core.config import settings
from app.core.environment.discovery import EnvironmentProbe

def test_inferred_device_type_manual_override():
    # 1. Test settings manual override (and length restriction <= 20)
    with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", "raspberry_pi_agent_long"):
        val = EnvironmentProbe.get_inferred_device_type()
        assert val == "raspberry_pi_agent_l" # Truncated to 20 chars

    with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", "custom_role"):
        val = EnvironmentProbe.get_inferred_device_type()
        assert val == "custom_role"

def test_inferred_device_type_android():
    # 2. Test Android environment detection via ANDROID_ROOT
    with patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
        with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", None):
            val = EnvironmentProbe.get_inferred_device_type()
            assert val == "android"

def test_inferred_device_type_macos():
    # 3. Test macOS detection when state is not awakened (Darwin fallback)
    with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", None):
        with patch("platform.system", return_value="Darwin"):
            with patch("app.core.environment.state.get_awakened_state", return_value=None):
                val = EnvironmentProbe.get_inferred_device_type()
                assert val == "desktop"

def test_inferred_device_type_embedded_via_proc():
    # 4. Test Raspberry Pi detection via /proc/device-tree/model
    mock_exists = lambda path: path in ("/proc/device-tree/model",)
    mock_open_data = "Raspberry Pi 4 Model B Rev 1.1"

    with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", None):
        with patch("os.path.exists", mock_exists):
            with patch("builtins.open", mock_open(read_data=mock_open_data)):
                with patch("app.core.environment.state.get_awakened_state", return_value=None):
                    with patch("platform.system", return_value="Linux"):
                        val = EnvironmentProbe.get_inferred_device_type()
                        assert val == "embedded"

def test_inferred_device_type_embedded_via_gpio():
    # 5. Test Raspberry Pi detection via /sys/class/gpio
    mock_exists = lambda path: path in ("/sys/class/gpio",)

    with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", None):
        with patch("os.path.exists", mock_exists):
            with patch("app.core.environment.state.get_awakened_state", return_value=None):
                with patch("platform.system", return_value="Linux"):
                    val = EnvironmentProbe.get_inferred_device_type()
                    assert val == "embedded"

def test_inferred_device_type_linux_desktop():
    # 6. Test Linux Desktop detection via DISPLAY env var
    with patch.dict(os.environ, {"DISPLAY": ":0"}):
        with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", None):
            with patch.object(settings, "ENABLE_ENVIRONMENT_CONTROLS", False):
                with patch("os.path.exists", return_value=False):
                    with patch("app.core.environment.state.get_awakened_state", return_value=None):
                        with patch("platform.system", return_value="Linux"):
                            val = EnvironmentProbe.get_inferred_device_type()
                            assert val == "desktop"

def test_inferred_device_type_server_fallback():
    # 7. Test headless Linux Server fallback
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(settings, "EVOCLOUD_DEVICE_TYPE", None):
            with patch.object(settings, "ENABLE_ENVIRONMENT_CONTROLS", False):
                with patch("os.path.exists", return_value=False):
                    with patch("app.core.environment.state.get_awakened_state", return_value=None):
                        with patch("platform.system", return_value="Linux"):
                            val = EnvironmentProbe.get_inferred_device_type()
                            assert val == "server"
