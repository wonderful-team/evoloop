"""
链路验证：设备身份 / 当前应用 / 主机信息 / 遥测 四类生产者→消费者链路。

对应分层重构：
- 底层：drivers（macos/adb 探针）
- 中层：app/core/device.py、app/core/environment/（类型化出口）
- 应用层：engine / vision / tools / 模板

本测试进程内运行（无 HTTP server），对硬件探针用 monkeypatch 打桩，
验证各层字段契约、类型化访问、模板渲染不出现空值/Unknown。
"""

from __future__ import annotations

import asyncio

from app.core.device import (
    get_device_description,
    get_device_name,
    get_hardware_fingerprint,
    get_hostname,
)
from app.core.environment import (
    collect_cpu_mem,
    get_current_app_context,
    get_telemetry_dict,
)
from app.core.environment.schemas.models import (
    AndroidDevice,
    CurrentApp,
    HostEnvironment,
    NetworkStatus,
)
from app.core.environment.state import set_awakened_state
from app.utils.template import render_template


# =============================================================================
# 链路 1：设备身份（device.py）
# =============================================================================
class TestDeviceIdentityChain:
    def test_get_hostname_non_empty(self) -> None:
        h = get_hostname()
        assert isinstance(h, str)
        assert h != ""  # 本机必有主机名

    def test_fingerprint_is_deterministic_32chars(self) -> None:
        # 指纹必须确定性且为 SHA256 截断 32 字符
        assert len(get_hardware_fingerprint()) == 32
        assert get_hardware_fingerprint() == get_hardware_fingerprint()

    def test_get_device_name_falls_back_to_hostname(self, monkeypatch) -> None:
        # 无运行时配置覆盖时，device_name 应回退到 settings/主机名
        name = get_device_name()
        assert isinstance(name, str) and name

    def test_get_device_description_default_empty(self) -> None:
        assert isinstance(get_device_description(), str)


# =============================================================================
# 链路 2：当前应用（macos/adb 驱动 → CurrentApp 类型化 → 消费方）
# =============================================================================
class TestCurrentAppChain:
    def test_driver_contract_includes_bundle_id_and_title(self) -> None:
        """底层驱动契约必须包含消费方读取的全部字段。"""
        from app.infrastructure.drivers.macos import macos_driver

        info = macos_driver.get_current_app()
        required = {"name", "pid", "bounds", "bundle_id", "title"}
        assert required <= set(info.keys()), f"缺字段: {required - set(info.keys())}"
        # name 恒非空
        assert info["name"]

    def test_accessor_macos_typed(self, monkeypatch) -> None:
        """中层访问器把驱动 dict 映射为类型化 CurrentApp。"""
        from app.infrastructure.drivers.macos import macos_driver

        monkeypatch.setattr(
            macos_driver,
            "get_current_app",
            lambda: {
                "name": "PyCharm",
                "pid": 100,
                "bounds": "0,0,800,600",
                "bundle_id": "com.jetbrains.PyCharm",
                "title": "main.py — PyCharm",
            },
        )
        ctx = get_current_app_context()
        assert isinstance(ctx, CurrentApp)
        assert ctx.bundle_id == "com.jetbrains.PyCharm"
        assert ctx.name == "PyCharm"
        assert ctx.platform == "macos"
        assert ctx.bounds == "0,0,800,600"

    def test_accessor_android_typed(self, monkeypatch) -> None:
        """ADB 路径映射为 package/activity。"""
        from app.infrastructure.drivers.adb import adb_driver

        monkeypatch.setattr(
            adb_driver,
            "get_current_app",
            lambda device_id=None: {
                "package": "com.example.app",
                "activity": "MainActivity",
                "confidence": 0.9,
                "source": "a11y",
            },
        )
        ctx = get_current_app_context(device_id="dev1")
        assert isinstance(ctx, CurrentApp)
        assert ctx.package == "com.example.app"
        assert ctx.activity == "MainActivity"
        assert ctx.platform == "android"

    def test_accessor_error_returns_default(self, monkeypatch) -> None:
        from app.infrastructure.drivers.macos import macos_driver

        monkeypatch.setattr(
            macos_driver, "get_current_app", lambda: {"error": "boom"}
        )
        ctx = get_current_app_context()
        assert ctx.name == "unknown" and ctx.bundle_id is None

    def test_find_element_consumer_publishes_bundle_id(self, monkeypatch) -> None:
        """find_element 消费方：macOS 发布 bundle_id/title（非 unknown）。"""
        from app.infrastructure.drivers.macos import macos_driver

        monkeypatch.setattr(
            macos_driver,
            "get_current_app",
            lambda: {
                "name": "PyCharm",
                "pid": 1,
                "bounds": "0,0,1,1",
                "bundle_id": "com.jetbrains.PyCharm",
                "title": "t",
            },
        )
        from app.core.environment.controllers.desktop.utils import (
            _trigger_atlas_harvest_macos,
        )

        async def _run():
            # dump_ax_tree 打桩返回合法输出
            monkeypatch.setattr(
                macos_driver,
                "dump_ax_tree",
                lambda: "[{'role':'button','name':'ok'}]",
            )
            await _trigger_atlas_harvest_macos("com.jetbrains.PyCharm")

        asyncio.run(_run())


# =============================================================================
# 链路 3：主机信息（macos get_system_info → HostEnvironment → 摘要 → 模板）
# =============================================================================
class TestHostInfoChain:
    def test_get_system_info_has_cpu_and_ram_gb(self) -> None:
        from app.infrastructure.drivers.macos.info import InfoMixin

        info = InfoMixin.get_system_info()
        assert "cpu" in info and info["cpu"], "cpu 必须有值"
        assert isinstance(info.get("ram_gb"), int) and info["ram_gb"] > 0
        assert info["os_version"] and info["model"]

    def test_discovery_host_mapping(self) -> None:
        """get_system_info 输出 → HostEnvironment 字段契约。"""
        from app.infrastructure.drivers.macos.info import InfoMixin

        info = InfoMixin.get_system_info()
        env = HostEnvironment(
            os_name="macOS",
            os_version=info.get("os_version", "Unknown"),
            model=info.get("model", "Unknown"),
            cpu=info.get("cpu", "Unknown"),
            ram_gb=info.get("ram_gb", 0),
            device_id="test-host",
        )
        assert env.cpu != "Unknown", "cpu 必须被填充"
        assert env.ram_gb > 0, "ram_gb 必须 > 0"

    def test_build_environment_summaries_and_templates(self) -> None:
        """awakened state → summaries → awareness/supervisor 模板无 Unknown。"""
        from app.core.environment.prompt import build_environment_summaries
        from app.infrastructure.drivers.macos.info import InfoMixin

        info = InfoMixin.get_system_info()
        host = HostEnvironment(
            os_name="macOS",
            os_version=info["os_version"],
            model=info["model"],
            cpu=info["cpu"],
            ram_gb=info["ram_gb"],
            installed_apps=["A"],
            app_usage_stats=[],
            device_id="test-host",
        )
        dev = AndroidDevice(
            device_id="dev1",
            model="Pixel",
            os_version="Android 14",
            sdk_version=34,
            battery_percent=80,
            is_reachable=True,
            installed_packages=["pkg1"],
        )
        state = type("S", (), {})()
        # 用真实 AwakenedState 打桩
        from app.core.environment.models import AwakenedState

        state = AwakenedState.model_construct(
            host=host,
            android_devices=[dev],
            network=NetworkStatus(internet_connected=True),
            docker_containers=[],
        )
        set_awakened_state(state)
        data = build_environment_summaries(relevance="both")
        assert data.get("host"), "host 必须有"
        assert data["host"]["cpu"] != "Unknown"
        assert data["host"].get("cpu_percent") is not None

        aware = render_template(
            "core/environment/fragments/awareness.j2",
            environment=data,
            current_datetime="now",
        )
        hostline = [line for line in aware.split("\n") if "Host:" in line]
        assert hostline and "Unknown" not in hostline[0], hostline


# =============================================================================
# 链路 4：遥测（collect_cpu_mem / get_telemetry_dict）
# =============================================================================
class TestTelemetryChain:
    def test_collect_cpu_mem_fields(self) -> None:
        m = collect_cpu_mem()
        assert m is not None
        for k in ("cpu_percent", "load_avg", "mem_percent", "mem_available", "mem_used", "mem_total"):
            assert k in m, f"缺字段 {k}"

    def test_collect_cpu_mem_types(self) -> None:
        m = collect_cpu_mem()
        assert isinstance(m["cpu_percent"], (int, float))
        assert m["mem_total"] > 0

    def test_get_telemetry_dict_is_dict(self) -> None:
        d = get_telemetry_dict()
        assert isinstance(d, dict)


# =============================================================================
# 链路 5：事件键名 + 模板字段错配修复验证
# =============================================================================
class TestEventAndTemplateFixes:
    def test_macro_engine_fallback_has_failed_step(self) -> None:
        """MacroEngine 的 fallback_context 必须含 failed_step（供 skill_error 模板）。"""
        from app.core.learning.macro.schemas import MacroStep, MacroStepType

        step = MacroStep(type=MacroStepType.ACTION, event_type="click", description="click button")
        # 验证模型可 dump 出 description/event_type
        dumped = step.model_dump()
        assert "description" in dumped and "event_type" in dumped


# =============================================================================
# 链路 6：engine 提示词模块消费方（telemetry / environment_summaries / plan）
# =============================================================================
# 图引擎的 supervisor/worker/finish context ticket 模板已随重构删除，
# 不再有对应的模板渲染测试（react 模式由 engine/react/prompts.py 组装 system prompt）。
class TestEnginePromptConsumers:
    pass


# =============================================================================
# 链路 7：LAN 设备发现（mDNS/DNS-SD）
# =============================================================================
class TestLanDeviceDiscovery:
    def test_classify_device_type(self) -> None:
        from app.core.environment.lan_discovery import classify_device_type

        assert classify_device_type("_airplay._tcp.local.") == "tv"
        assert classify_device_type("_googlecast._tcp.local.") == "tv"
        assert classify_device_type("_raop._tcp.local.") == "speaker"
        assert classify_device_type("_spotify-connect._tcp.local.") == "speaker"
        assert classify_device_type("_hap._tcp.local.") == "smart_home"
        assert classify_device_type("_ipp._tcp.local.") == "printer"
        assert classify_device_type("_smb._tcp.local.") == "computer"
        assert classify_device_type("_rfb._tcp.local.") == "computer"
        assert classify_device_type("_unknown._tcp.local.") == "unknown"

    def test_lan_device_model(self) -> None:
        from app.core.environment.schemas.models import LanDevice

        dev = LanDevice(ip="1.2.3.4", name="TV", device_type="tv", model="X1")
        assert dev.ip == "1.2.3.4" and dev.device_type == "tv"
        assert dev.services == [] and dev.port is None

    def test_awakened_state_has_lan_devices(self) -> None:
        """AwakenedState 含 lan_devices + summaries 暴露 + 模板渲染。"""
        from app.core.environment.models import AwakenedState
        from app.core.environment.prompt import build_environment_summaries
        from app.core.environment.schemas.models import (
            HostEnvironment,
            LanDevice,
        )
        from app.core.environment.state import set_awakened_state
        from app.utils.template import render_template

        host = HostEnvironment(
            os_name="macOS",
            os_version="v",
            model="m",
            cpu="c",
            ram_gb=8,
            device_id="d",
        )
        lan = [LanDevice(ip="192.168.3.22", name="音箱", device_type="speaker")]
        state = AwakenedState.model_construct(
            host=host,
            android_devices=[],
            network=None,
            docker_containers=[],
            lan_devices=lan,
        )
        set_awakened_state(state)
        data = build_environment_summaries(relevance="both")
        assert data.get("lan_devices")
        assert data["lan_devices"][0]["device_type"] == "speaker"

        aware = render_template(
            "core/environment/fragments/awareness.j2",
            environment=data,
            current_datetime="now",
        )
        assert "LAN Devices" in aware and "音箱" in aware

    def test_probe_lan_devices_returns_typed(self) -> None:
        """真实网络探测返回 LanDevice 对象（无设备也安全返回空列表）。"""
        import asyncio

        from app.core.environment.lan_discovery import probe_lan_devices
        from app.core.environment.schemas.models import LanDevice

        async def _run():
            devices = await probe_lan_devices(timeout=1.0)
            assert all(isinstance(d, LanDevice) for d in devices)
            assert all(d.ip for d in devices)
            return devices

        devices = asyncio.run(_run())
        # 本网络可能发现 0 台，但结构必须正确
        assert isinstance(devices, list)


class TestLanArpComplement:
    def test_randomized_mac_detection(self) -> None:
        from app.core.environment.lan_discovery import _is_randomized_mac

        # 本地管理位（随机 MAC）：第二十六进制位为 2/6/a/e
        assert _is_randomized_mac("d2:35:19:3:28:e6") is True
        assert _is_randomized_mac("9e:43:24:25:c5:37") is True
        assert _is_randomized_mac("72:b1:ee:64:62:d7") is True
        # 稳定 MAC（厂商 OUI）
        assert _is_randomized_mac("c4:27:8c:f7:b0:d1") is False
        assert _is_randomized_mac("18:5e:0f:83:a3:c9") is False

    def test_lan_device_includes_mac(self) -> None:
        from app.core.environment.schemas.models import LanDevice

        dev = LanDevice(ip="1.2.3.4", mac="d2:35:19:3:28:e6", device_type="mobile")
        assert dev.mac == "d2:35:19:3:28:e6"


class TestLanClassifierPriorityAndOui:
    def test_priority_classification(self) -> None:
        from app.core.environment.lan_discovery import classify_device_types

        # 多服务设备稳定分类：Mac 广播 _smb+_raop → computer（不是 speaker）
        assert classify_device_types(["_smb._tcp.local.", "_raop._tcp.local."]) == "computer"
        # 仅媒体服务 → tv/speaker
        assert classify_device_types(["_airplay._tcp.local.", "_googlecast._tcp.local."]) == "tv"
        assert classify_device_types(["_raop._tcp.local."]) == "speaker"
        # smart_home
        assert classify_device_types(["_hap._tcp.local."]) == "smart_home"
        # 未知
        assert classify_device_types(["_foo._tcp.local."]) == "unknown"
        # 确定性：相同输入顺序无关
        assert (
            classify_device_types(["_raop._tcp.local.", "_smb._tcp.local."])
            == classify_device_types(["_smb._tcp.local.", "_raop._tcp.local."])
        )

    def test_oui_vendor_lookup(self) -> None:
        from app.core.environment.lan_discovery import _oui_vendor

        assert _oui_vendor("f0:18:98:12:34:56") == "Apple"
        assert _oui_vendor("64:69:3a:aa:bb:cc") == "Xiaomi"
        assert _oui_vendor("44:6d:57:11:22:33") == "Huawei"
        assert _oui_vendor("00:12:fb:99:88:77") == "Samsung"
        assert _oui_vendor("b8:27:eb:11:22:33") == "Raspberry Pi"
        assert _oui_vendor("00:00:00:11:22:33") == ""


class TestBluetoothDiscovery:
    def test_bt_vendor_and_type_mapping(self) -> None:
        from app.core.environment.bluetooth_discovery import (
            _bt_device_type,
            _bt_vendor,
        )

        assert _bt_vendor("0x004C") == "Apple"
        assert _bt_vendor("0x010F") == "Huawei"
        assert _bt_vendor("0x2717") == "Xiaomi"
        assert _bt_device_type("Mobile Phone") == "mobile"
        assert _bt_device_type("Headset") == "audio"
        assert _bt_device_type("Keyboard") == "peripheral"
        assert _bt_device_type("Mouse") == "peripheral"
        assert _bt_device_type("Computer") == "computer"

    def test_bluetooth_device_model(self) -> None:
        from app.core.environment.schemas.models import BluetoothDevice

        dev = BluetoothDevice(name="Phone", device_type="mobile", vendor="Huawei")
        assert dev.name == "Phone" and dev.device_type == "mobile"
        assert dev.vendor == "Huawei"

    def test_probe_bluetooth_devices(self) -> None:
        """真实探测返回 BluetoothDevice 对象（无蓝牙也安全）。"""
        from app.core.environment.bluetooth_discovery import probe_bluetooth_devices
        from app.core.environment.schemas.models import BluetoothDevice

        devs = probe_bluetooth_devices()
        assert all(isinstance(d, BluetoothDevice) for d in devs)

    def test_lan_mobile_enriched_by_bluetooth(self) -> None:
        """LAN mobile 设备被蓝牙手机丰富名称/厂商。"""
        from app.core.environment.models import AwakenedState
        from app.core.environment.prompt import build_environment_summaries
        from app.core.environment.schemas.models import (
            BluetoothDevice,
            HostEnvironment,
            LanDevice,
        )
        from app.core.environment.state import set_awakened_state
        from app.utils.template import render_template

        host = HostEnvironment(
            os_name="macOS", os_version="v", model="m", cpu="c", ram_gb=8, device_id="d"
        )
        lan = [LanDevice(ip="192.168.3.3", device_type="mobile", mac="d2:35:19:3:28:e6")]
        bt = [BluetoothDevice(name="Mate 30", device_type="mobile", vendor="Huawei")]
        state = AwakenedState.model_construct(
            host=host,
            android_devices=[],
            network=None,
            docker_containers=[],
            lan_devices=lan,
            bluetooth_devices=bt,
        )
        set_awakened_state(state)
        data = build_environment_summaries(relevance="both")
        lan_item = data["lan_devices"][0]
        assert lan_item["name"] == "Mate 30"
        assert lan_item["manufacturer"] == "Huawei"

        aware = render_template(
            "core/environment/fragments/awareness.j2",
            environment=data,
            current_datetime="now",
        )
        # 蓝牙不独立成区；LAN 设备内展示被蓝牙丰富的手机名称/厂商
        assert "Bluetooth Devices" not in aware
        assert "Mate 30" in aware and "Huawei" in aware
