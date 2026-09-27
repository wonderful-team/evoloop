"""Final coverage push: mobile screenshot cropping, platform inputs,
element_visible conditions and the collect DETAIL phase."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.learning.macro.engine import MacroEngine
from app.core.learning.macro.schemas import (
    MacroScript,
    MacroSource,
    MacroStep,
    MacroStepType,
)


@pytest.fixture(autouse=True)
def _mock_activity(monkeypatch):
    from app.core.learning.macro.engine import activity_monitor

    monkeypatch.setattr(activity_monitor, "check_cancellation", AsyncMock())
    monkeypatch.setattr(activity_monitor, "log_event", AsyncMock())


def _step(event_type, source, step_number=1, **payload):
    return MacroStep(
        type=MacroStepType.ACTION,
        event_type=event_type,
        source=source,
        step_number=step_number,
        payload=payload,
    )


class TestCropMobileScreenshot:
    @pytest.mark.asyncio
    async def test_crop_found_element(self, tmp_path, monkeypatch):
        from app.core.learning.macro.engine import ExtractionMixin

        filepath = tmp_path / "shot.png"
        filepath.write_bytes(b"fake")

        a11y = SimpleNamespace(
            success=True,
            elements=[
                SimpleNamespace(
                    text="btn",
                    x=50, y=60, width=10, height=20,
                    metadata={"resource_id": ""},
                )
            ],
        )
        monkeypatch.setattr(
            "app.infrastructure.vision.providers.native.android_a11y.android_a11y_provider.process",
            AsyncMock(return_value=a11y),
        )
        img = MagicMock()
        img.__enter__.return_value = img
        cropped = MagicMock()
        img.crop.return_value = cropped
        monkeypatch.setattr("PIL.Image.open", lambda *a, **k: img)

        result = await ExtractionMixin._crop_mobile_screenshot(str(filepath), "btn")
        assert result is not None and result != str(filepath)
        img.crop.assert_called_once()

    @pytest.mark.asyncio
    async def test_crop_not_found_returns_original(self, tmp_path, monkeypatch):
        from app.core.learning.macro.engine import ExtractionMixin

        filepath = tmp_path / "shot.png"
        filepath.write_bytes(b"fake")
        a11y = SimpleNamespace(success=True, elements=[])
        monkeypatch.setattr(
            "app.infrastructure.vision.providers.native.android_a11y.android_a11y_provider.process",
            AsyncMock(return_value=a11y),
        )
        result = await ExtractionMixin._crop_mobile_screenshot(str(filepath), "nope")
        assert result == str(filepath)


class TestPlatformInput:
    @pytest.mark.asyncio
    async def test_mobile_input(self, monkeypatch):
        from app.core.environment.controllers.mobile import MobileController

        monkeypatch.setattr(MobileController, "execute", AsyncMock(return_value="OK"))
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[_step("input", MacroSource.MOBILE, text="hi")]),
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_desktop_input(self, monkeypatch):
        from app.core.environment.controllers.desktop import DesktopController

        monkeypatch.setattr(DesktopController, "execute", AsyncMock(return_value="OK"))
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[_step("input", MacroSource.DESKTOP, text="hi")]),
            skip_activity_log=True,
        )
        assert ok is True


class TestElementVisible:
    @pytest.mark.asyncio
    async def test_dom_visible(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.learning.macro.engine import ControlMixin

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="visible=True")
        )
        result = await ControlMixin._evaluate_condition(
            "element_visible", "#x", MacroSource.DOM
        )
        assert result is True


class TestCollectDetailPhase:
    @pytest.mark.asyncio
    async def test_detail_processes_items(self, tmp_path, monkeypatch):
        import json

        from app.core.learning.macro.engine import LoopMixin

        state_file = tmp_path / "collect.json"
        state_file.write_text(
            json.dumps(
                {
                    "items": [
                        {"signature": "s1", "status": "pending", "tap_x": 1, "tap_y": 2},
                    ],
                    "phase": "detail",
                }
            )
        )

        done = []

        class _Loop(LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                iter_params = args[2] if len(args) > 2 else {}
                done.append(iter_params.get("item"))
                return True, "", None

        monkeypatch.setattr(
            "app.core.environment.controllers.mobile.MobileController.execute",
            AsyncMock(return_value="OK"),
        )
        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            step_number=1,
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.MOBILE)],
        )
        ok, msg, _ = await _Loop._handle_collect_loop(
            "t",
            step,
            {
                "state_file": str(state_file),
                "detail_config": {"limit": 10, "wait_after_tap_ms": 1},
            },
            {},
            {},
            disable_ocr=True,
            collect_mode="detail",
        )
        assert ok is True
        assert len(done) == 1


class TestLoopRetry:
    @pytest.mark.asyncio
    async def test_network_error_retries_then_succeeds(self, monkeypatch):
        from app.core.learning.macro.engine import LoopMixin

        monkeypatch.setattr(
            "app.core.learning.macro.engine.loops.asyncio.sleep", AsyncMock()
        )

        calls = {"n": 0}

        class _Loop(LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    return False, "network timeout", None
                return True, "", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            step_number=1,
            payload={"items_key": "items", "max_retries": 2, "backoff_base": 1},
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.MOBILE)],
        )
        ok, msg, _ = await _Loop._handle_loop(
            "t", step, step.payload, {"items": ["a"]}, {}
        )
        assert ok is True
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_functional_error_fails(self):
        from app.core.learning.macro.engine import LoopMixin

        class _Loop(LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                return False, "element missing", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            step_number=1,
            payload={"items_key": "items", "max_retries": 0},
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.MOBILE)],
        )
        ok, msg, meta = await _Loop._handle_loop(
            "t", step, step.payload, {"items": ["a"]}, {}
        )
        assert ok is False  # functional errors are not retried / DLQ'd

    @pytest.mark.asyncio
    async def test_exception_exhausts_retries_to_dlq(self, monkeypatch):
        from app.core.learning.macro.engine import LoopMixin

        monkeypatch.setattr(
            "app.core.learning.macro.engine.loops.asyncio.sleep", AsyncMock()
        )

        class _Loop(LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                raise RuntimeError("boom")

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            step_number=1,
            payload={"items_key": "items", "max_retries": 1, "backoff_base": 1},
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.MOBILE)],
        )
        ok, msg, meta = await _Loop._handle_loop(
            "t", step, step.payload, {"items": ["a"]}, {}
        )
        assert ok is True  # completes with the item in DLQ
        assert meta is not None and "dlq" in meta


class TestDesktopMoreActions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type,payload",
        [
            ("key_press", {"key": "Enter"}),
            ("scroll", {"direction": "down"}),
            ("applescript", {"script": "tell app \"X\" to quit"}),
        ],
    )
    async def test_desktop_actions(self, monkeypatch, event_type, payload):
        from app.core.environment.controllers.desktop import DesktopController

        monkeypatch.setattr(DesktopController, "execute", AsyncMock(return_value="OK"))
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(
                steps=[_step(event_type, MacroSource.DESKTOP, **payload)]
            ),
            skip_activity_log=True,
        )
        assert ok is True


class TestControlMore:
    @pytest.mark.asyncio
    async def test_if_missing_condition_skips(self):
        from app.core.learning.macro.engine import ControlMixin

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                raise AssertionError("should not run")

        step = MacroStep(type=MacroStepType.IF, source=MacroSource.DOM, step_number=1)
        ok, msg, _ = await _Ctrl._handle_control_flow("t", step, {}, {}, {})
        assert ok is True

    @pytest.mark.asyncio
    async def test_loop_str_max_iterations(self):
        from app.core.learning.macro.engine import ControlMixin

        calls = {"n": 0}

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                calls["n"] += 1
                return True, "", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.DOM,
            step_number=1,
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
        )
        ok, msg, _ = await _Ctrl._handle_control_flow(
            "t", step, {"max_iterations": "3"}, {}, {}
        )
        assert ok is True
        assert calls["n"] == 3


class TestDumpMore:
    @pytest.mark.asyncio
    async def test_include_state_items(self, tmp_path):
        import json

        from app.core.learning.macro.engine import DumpMixin

        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"items": [{"signature": "s1"}]}))
        extracted = {"collect_results": {"state_file": str(state_file)}}
        out_path = tmp_path / "out.json"
        await DumpMixin._handle_dump(
            "t",
            {"sink_type": "file", "path": str(out_path), "include_state_items": True},
            extracted,
        )
        import json

        dumped = json.load(open(out_path))
        assert dumped["batch_items"] == [{"signature": "s1"}]

    @pytest.mark.asyncio
    async def test_mcp_target_missing(self, monkeypatch):
        from app.core.learning.macro.engine import DumpMixin

        monkeypatch.setattr(
            "app.core.mcp.mcp_client_manager.get_tools", AsyncMock(return_value=[])
        )
        await DumpMixin._dump_to_mcp(
            "t",
            {"mcp_server": "supabase", "mcp_tool": "missing_tool"},
            {"a": 1},
        )


class TestControlLoopBranches:
    @pytest.mark.asyncio
    async def test_loop_no_steps(self):
        from app.core.learning.macro.engine import ControlMixin

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

        step = MacroStep(type=MacroStepType.LOOP, source=MacroSource.DOM, steps=[])
        ok, msg, _ = await _Ctrl._handle_control_flow("t", step, {}, None, {})
        assert ok is True

    @pytest.mark.asyncio
    async def test_loop_invalid_str_max_iters(self):
        from app.core.learning.macro.engine import ControlMixin

        calls = {"n": 0}

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                calls["n"] += 1
                return True, "", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.DOM,
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
        )
        await _Ctrl._handle_control_flow("t", step, {"max_iterations": "abc"}, {}, {})
        assert calls["n"] == 5  # invalid str falls back to 5

    @pytest.mark.asyncio
    async def test_loop_condition_false_breaks(self):
        from app.core.learning.macro.engine import ControlMixin
        from app.core.learning.macro.schemas import MacroCondition

        calls = {"n": 0}

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

            @classmethod
            async def _evaluate_condition(cls, *a, **k):
                return False

            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                calls["n"] += 1
                return True, "", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.DOM,
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
            condition=MacroCondition(type="element_exists", target_selector="#x"),
        )
        await _Ctrl._handle_control_flow("t", step, {}, {}, {})
        assert calls["n"] == 0

    @pytest.mark.asyncio
    async def test_loop_failure_returns_fallback(self):
        from app.core.learning.macro.engine import ControlMixin

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                return False, "boom", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.DOM,
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
        )
        ok, msg, fallback = await _Ctrl._handle_control_flow("t", step, {}, {}, {})
        assert ok is False
        assert fallback is not None and "loop_progress" in fallback


class TestEvaluateMore:
    @pytest.mark.asyncio
    async def test_element_visible_mobile(self, monkeypatch):
        from app.core.environment.controllers.mobile import MobileController
        from app.core.learning.macro.engine import ControlMixin

        monkeypatch.setattr(
            MobileController, "execute", AsyncMock(return_value="hello #x world")
        )
        assert (
            await ControlMixin._evaluate_condition(
                "element_visible", "#x", MacroSource.MOBILE
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_element_visible_desktop(self, monkeypatch):
        from app.core.environment.controllers.desktop import DesktopController
        from app.core.learning.macro.engine import ControlMixin

        monkeypatch.setattr(DesktopController, "execute", AsyncMock(return_value="true"))
        assert (
            await ControlMixin._evaluate_condition(
                "element_visible", "Btn", MacroSource.DESKTOP
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_text_contains_dom(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.learning.macro.engine import ControlMixin

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="hello keyword world")
        )
        assert (
            await ControlMixin._evaluate_condition(
                "text_contains", "keyword", MacroSource.DOM
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_has_more_items_true(self):
        from app.core.learning.macro.engine import ControlMixin

        assert (
            await ControlMixin._evaluate_condition(
                "has_more_items", None, MacroSource.DOM
            )
            is True
        )


class TestLoopMore:
    @pytest.mark.asyncio
    async def test_fuzzy_match_single_list(self):
        from app.core.learning.macro.engine import LoopMixin

        calls = []

        class _Loop(LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                iter_params = args[2] if len(args) > 2 else {}
                calls.append(iter_params.get("item"))
                return True, "", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            payload={"items_key": "items"},
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.MOBILE)],
        )
        ok, msg, _ = await _Loop._handle_loop(
            "t", step, step.payload, {}, {"goods": ["g1", "g2"]}
        )
        assert ok is True
        assert calls == ["g1", "g2"]

    @pytest.mark.asyncio
    async def test_detail_no_pending(self, tmp_path):
        import json

        from app.core.learning.macro.engine import LoopMixin

        state_file = tmp_path / "c.json"
        state_file.write_text(
            json.dumps({"items": [{"signature": "s1", "status": "done"}], "phase": "detail"})
        )
        step = MacroStep(type=MacroStepType.LOOP, source=MacroSource.MOBILE, steps=[])
        ok, msg, _ = await LoopMixin._handle_collect_loop(
            "t", step, {"state_file": str(state_file)}, {}, {}, True, "detail"
        )
        assert ok is True
        assert "No pending items" in msg

    def test_extract_collect_items_from_xml(self):
        from app.core.learning.macro.engine import LoopMixin

        xml = '<node text="Apple ￥10.00" bounds="[0,0][100,50]"/>'
        items = LoopMixin._extract_collect_items_from_xml(
            xml, {"type": "price", "pattern": "￥[0-9,.]+"}, {"offset_y": -200, "height": 200, "max_features": 4}
        )
        assert len(items) >= 1
        assert items[0]["text"] == "Apple ￥10.00"


class TestDumpMore2:
    @pytest.mark.asyncio
    async def test_mcp_data_mapping(self, monkeypatch):
        from types import SimpleNamespace

        from app.core.learning.macro.engine import DumpMixin

        target = SimpleNamespace(
            name="mcp__supabase__upsert",
            ainvoke=AsyncMock(return_value={"ok": True}),
        )
        monkeypatch.setattr(
            "app.core.mcp.mcp_client_manager.get_tools",
            AsyncMock(return_value=[target]),
        )
        await DumpMixin._dump_to_mcp(
            "t",
            {
                "mcp_server": "supabase",
                "mcp_tool": "upsert",
                "data_mapping": {"name": "title"},
            },
            {"title": "hello"},
        )
        target.ainvoke.assert_awaited()

    @pytest.mark.asyncio
    async def test_webhook_no_url(self):
        from app.core.learning.macro.engine import DumpMixin

        await DumpMixin._dump_to_webhook("t", {"method": "POST"}, {"a": 1})


class TestUnwrapControllerValue:
    def test_non_string_passthrough(self):
        from app.core.learning.macro.engine.extraction import _unwrap_controller_value

        assert _unwrap_controller_value(123) == 123
        assert _unwrap_controller_value(None) is None

    def test_error_returns_none(self):
        from app.core.learning.macro.engine.extraction import _unwrap_controller_value

        assert _unwrap_controller_value("❌ Execution failed") is None

    def test_js_result_stripped(self):
        from app.core.learning.macro.engine.extraction import _unwrap_controller_value

        assert _unwrap_controller_value("JS result: 42") == "42"

    def test_success_envelope_details(self):
        from app.core.learning.macro.engine.extraction import _unwrap_controller_value

        assert _unwrap_controller_value("✅ ok\n\ndetails here") == "details here"

    def test_success_no_details_empty(self):
        from app.core.learning.macro.engine.extraction import _unwrap_controller_value

        assert _unwrap_controller_value("✅ ok") == ""

    def test_plain_string_passthrough(self):
        from app.core.learning.macro.engine.extraction import _unwrap_controller_value

        assert _unwrap_controller_value("hello") == "hello"


class TestNativeMore:
    @pytest.mark.asyncio
    async def test_missing_script_path(self):
        from app.core.learning.macro.engine import NativeMixin

        result = await NativeMixin._handle_native("t", {}, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_sync_state(self, tmp_path, monkeypatch):
        import json

        from app.core.learning.macro.engine import NativeMixin

        state = tmp_path / "state.json"
        state.write_text(json.dumps({"items": [{"id": 1}]}))

        fake = AsyncMock()
        fake.communicate = AsyncMock(return_value=(b"", b""))
        fake.returncode = 0
        monkeypatch.setattr(
            "app.core.atlas.script_gate.check_native_allowed", lambda *a: True
        )
        import app.core.learning.macro.engine.native as native_mod

        monkeypatch.setattr(
            native_mod.asyncio,
            "create_subprocess_exec",
            AsyncMock(return_value=fake),
        )
        extracted = {}
        await NativeMixin._handle_native(
            "t", {"script_path": "/tmp/s.py", "sync_state": str(state)}, extracted
        )
        assert extracted["batch_items"] == [{"id": 1}]
