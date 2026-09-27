"""Coverage for engine internals: bash steps, dump sinks, extraction,
IF branching and more browser action branches."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.environment.controllers.browser.advanced import BrowserAdvancedMixin
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


class TestBash:
    async def _run(self, payload):
        from app.core.learning.macro.engine import BashMixin

        extracted = {}
        await BashMixin._execute_bash_step("t", payload, extracted)
        return extracted

    @pytest.mark.asyncio
    async def test_missing_command_raises(self):
        from app.core.learning.macro.engine import BashMixin

        with pytest.raises(ValueError):
            await BashMixin._execute_bash_step("t", {"key": "out"}, {})

    @pytest.mark.asyncio
    async def test_success(self):
        fake = AsyncMock()
        fake.communicate = AsyncMock(return_value=(b"hello\n", b""))
        fake.returncode = 0
        with patch(
            "app.core.learning.macro.engine.bash.asyncio.create_subprocess_shell",
            return_value=fake,
        ):
            extracted = await self._run({"command": "echo hello", "key": "out"})
        assert extracted["out"] == "hello"

    @pytest.mark.asyncio
    async def test_nonzero_rc_raises(self):
        fake = AsyncMock()
        fake.communicate = AsyncMock(return_value=(b"", b"boom"))
        fake.returncode = 1
        with patch(
            "app.core.learning.macro.engine.bash.asyncio.create_subprocess_shell",
            return_value=fake,
        ):
            with pytest.raises(ValueError):
                await self._run({"command": "false", "key": "out"})

    @pytest.mark.asyncio
    async def test_nonzero_rc_continue_on_error(self):
        fake = AsyncMock()
        fake.communicate = AsyncMock(return_value=(b"", b"boom"))
        fake.returncode = 1
        with patch(
            "app.core.learning.macro.engine.bash.asyncio.create_subprocess_shell",
            return_value=fake,
        ):
            extracted = await self._run(
                {"command": "false", "key": "out", "continue_on_error": True}
            )
        assert "Exit code 1" in extracted["out"]


class TestBashOutputPropagation:
    @pytest.mark.asyncio
    async def test_bash_output_available_to_downstream_placeholder(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.learning.macro.engine import MacroEngine

        captured = {}

        async def fake_browser_execute(*, action, script=None, **_kwargs):
            if action == "run_js":
                captured["script"] = script
                return 'JS result: {"received":["a","b"]}'
            return "OK"

        monkeypatch.setattr(BrowserController, "execute", fake_browser_execute)

        script = MacroScript(
            steps=[
                MacroStep(
                    type=MacroStepType.BASH,
                    payload={"command": "echo '[\"a\",\"b\"]'", "key": "itemids"},
                    step_number=1,
                ),
                MacroStep(
                    type=MacroStepType.EXTRACT,
                    event_type="run_js",
                    extract_type="run_js",
                    source=MacroSource.DOM,
                    key="result",
                    payload={"script": "() => JSON.stringify({received: {{itemids}}})"},
                    step_number=2,
                ),
            ]
        )

        ok, msg, data = await MacroEngine.execute(
            "t", script, params={}, skip_activity_log=True
        )

        assert ok is True
        assert captured.get("script") is not None
        assert '["a","b"]' in captured["script"]
        assert "{{itemids}}" not in captured["script"]


class TestDump:
    @pytest.mark.asyncio
    async def test_dump_to_file(self, tmp_path):
        from app.core.learning.macro.engine import DumpMixin

        path = tmp_path / "out.json"
        extracted = {"title": "x"}
        await DumpMixin._handle_dump(
            "t", {"sink_type": "file", "path": str(path)}, extracted
        )
        import json

        assert json.load(open(path)) == {"title": "x"}


class TestIfBranching:
    @pytest.mark.asyncio
    async def test_if_true_executes_then(self, monkeypatch):
        from app.core.learning.macro.engine import ControlMixin

        taken = []

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

            @classmethod
            async def _evaluate_condition(cls, *a, **k):
                return True

            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                taken.append("then")
                return True, "", None

        step = MacroStep(
            type=MacroStepType.IF,
            source=MacroSource.DOM,
            condition=__import__(
                "app.core.learning.macro.schemas", fromlist=["MacroCondition"]
            ).MacroCondition(type="element_exists", target_selector="#x"),
            then_steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
            else_steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
        )
        ok, msg, _ = await _Ctrl._handle_control_flow("t", step, {}, {}, {})
        assert ok is True
        assert taken == ["then"]

    @pytest.mark.asyncio
    async def test_if_false_executes_else(self, monkeypatch):
        from app.core.learning.macro.engine import ControlMixin

        taken = []

        class _Ctrl(ControlMixin):
            @classmethod
            def _inject_params(cls, value, params):
                return value

            @classmethod
            async def _evaluate_condition(cls, *a, **k):
                return False

            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                taken.append("else")
                return True, "", None

        step = MacroStep(
            type=MacroStepType.IF,
            source=MacroSource.DOM,
            condition=__import__(
                "app.core.learning.macro.schemas", fromlist=["MacroCondition"]
            ).MacroCondition(type="element_exists", target_selector="#x"),
            then_steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
            else_steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
        )
        ok, msg, _ = await _Ctrl._handle_control_flow("t", step, {}, {}, {})
        assert taken == ["else"]


class TestBrowserMore:
    @pytest.mark.asyncio
    async def test_navigate(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(BrowserController, "execute", AsyncMock(return_value="OK"))
        script = MacroScript(
            steps=[
                MacroStep(
                    type=MacroStepType.ACTION,
                    event_type="navigate",
                    source=MacroSource.DOM,
                    payload={"url": "https://x.com"},
                )
            ]
        )
        ok, msg, _ = await MacroEngine.execute("t", script, skip_activity_log=True)
        assert ok is True


class TestExtraction:
    @pytest.mark.asyncio
    async def test_handle_extraction(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.learning.macro.schemas import ExtractType

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="hello text")
        )
        step = MacroStep(
            type=MacroStepType.EXTRACT,
            event_type="get_text",
            extract_type=ExtractType.GET_TEXT,
            source=MacroSource.DOM,
            payload={},
        )
        extracted = {}
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[step]),
            extracted_data=extracted,
            skip_activity_log=True,
        )
        assert ok is True


class TestCollectListPhase:
    @pytest.mark.asyncio
    async def test_collects_items_from_xml(self, tmp_path, monkeypatch):
        from app.core.learning.macro.engine import LoopMixin

        items = [
            {"signature": "sig1", "status": "pending", "tap_x": 10, "tap_y": 20},
            {"signature": "sig2", "status": "pending", "tap_x": 30, "tap_y": 40},
        ]
        monkeypatch.setattr(
            "app.infrastructure.drivers.adb.adb_driver.dump_ui",
            lambda *a, **k: "<node/>",
        )
        monkeypatch.setattr(
            LoopMixin, "_extract_collect_items_from_xml", lambda *a, **k: items
        )
        monkeypatch.setattr(
            "app.core.environment.controllers.mobile.MobileController.execute",
            AsyncMock(return_value="OK"),
        )

        state_file = tmp_path / "collect.json"
        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            step_number=1,
            steps=[],
        )
        extracted = {}
        ok, msg, meta = await LoopMixin._handle_collect_loop(
            "t",
            step,
            {"state_file": str(state_file), "list_config": {}},
            {},
            extracted,
            disable_ocr=True,
            collect_mode="list",
        )
        assert ok is True
        assert "List collection complete: 2 items" in msg
        assert len(extracted["collected_items"]) == 2
        assert state_file.exists()


class TestMobileExtraction:
    @pytest.mark.asyncio
    async def test_mobile_gui_extract(self, tmp_path, monkeypatch):
        from app.core.environment.controllers.mobile import MobileController
        from app.core.learning.macro.schemas import ExtractType

        monkeypatch.setattr(
            MobileController, "execute", AsyncMock(return_value="[{'key': 'title'}]")
        )
        step = MacroStep(
            type=MacroStepType.EXTRACT,
            event_type="dump_ui",
            extract_type=ExtractType.GUI_EXTRACT,
            source=MacroSource.MOBILE,
            step_number=1,
            payload={"key": "gui"},
        )
        extracted = {}
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[step]),
            extracted_data=extracted,
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_desktop_gui_extract(self, tmp_path, monkeypatch):
        from app.core.environment.controllers.desktop import DesktopController
        from app.core.learning.macro.schemas import ExtractType

        monkeypatch.setattr(
            DesktopController, "execute", AsyncMock(return_value="[{'key': 'x'}]")
        )
        step = MacroStep(
            type=MacroStepType.EXTRACT,
            event_type="dump_ui",
            extract_type=ExtractType.GUI_EXTRACT,
            source=MacroSource.DESKTOP,
            step_number=1,
            payload={"key": "gui"},
        )
        extracted = {}
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[step]),
            extracted_data=extracted,
            skip_activity_log=True,
        )
        assert ok is True


class TestRunJsErrorPropagation:
    @pytest.mark.asyncio
    async def test_run_js_syntax_error_returns_error_response(self):
        class FakePage:
            async def evaluate(self, script):
                raise Exception("Page.evaluate: SyntaxError: Unexpected token ';'")

        res = await BrowserAdvancedMixin._handle_advanced(
            "run_js", page=FakePage(), script="const x = ;"
        )
        assert res.startswith("❌")
        assert "run_js failed" in res
        assert "SyntaxError" in res

    @pytest.mark.asyncio
    async def test_run_js_error_fails_macro(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        async def fake_execute(*, action, _script=None, **_kwargs):
            if action == "run_js":
                return "❌ run_js failed\n\nPage.evaluate: SyntaxError: Unexpected token ';'"
            return "OK"

        monkeypatch.setattr(BrowserController, "execute", fake_execute)

        script = MacroScript(
            steps=[
                MacroStep(
                    type=MacroStepType.EXTRACT,
                    event_type="run_js",
                    extract_type="run_js",
                    source=MacroSource.DOM,
                    key="data",
                    payload={"script": "const x = ;"},
                    step_number=1,
                ),
            ]
        )
        ok, msg, _ = await MacroEngine.execute("t", script, skip_activity_log=True)
        assert ok is False
        assert "run_js failed" in msg


class TestInject:
    def test_inject_params(self):
        from app.core.learning.macro.engine import MacroEngine

        assert MacroEngine._inject_params("{{name}}", {"name": "x"}) == "x"
        assert MacroEngine._inject_params("{{parameters.y}}", {"y": 2}) == "2"
        assert MacroEngine._inject_params("a {{nested.k}} b", {"nested": {"k": "v"}}) == "a v b"
        assert MacroEngine._inject_params("{{unknown}}", {}) == ""
        assert MacroEngine._inject_params(None, {}) is None
        assert MacroEngine._inject_params("plain", None) == "plain"

    def test_inject_payload_params(self):
        from app.core.learning.macro.engine import MacroEngine

        payload = {"url": "{{base_url}}/x", "tags": ["{{t}}"]}
        injected = MacroEngine._inject_payload_params(payload, {"base_url": "http://a", "t": "z"})
        assert injected["url"] == "http://a/x"
        assert injected["tags"] == ["z"]

    @pytest.mark.asyncio
    async def test_navigate_unresolved_base_url(self, monkeypatch):
        from app.core.learning.macro.engine import MacroEngine
        from app.core.learning.macro.schemas import (
            MacroScript,
            MacroSource,
            MacroStep,
            MacroStepType,
        )

        step = MacroStep(
            type=MacroStepType.ACTION,
            event_type="navigate",
            source=MacroSource.DOM,
            step_number=1,
            payload={"url": "{{base_url}}/shop.html"},
        )
        ok, msg, _ = await MacroEngine.execute(
            "t", MacroScript(steps=[step]), skip_activity_log=True
        )
        assert ok is False
        assert "base_url" in msg or "未解析" in msg or "站点地址" in msg

    @pytest.mark.asyncio
    async def test_debug_screenshot(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.learning.macro.engine import MacroEngine
        from app.core.learning.macro.schemas import MacroSource

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="/tmp/debug.png")
        )
        assert await MacroEngine._debug_screenshot(MacroSource.DOM) == "/tmp/debug.png"
        assert await MacroEngine._debug_screenshot(MacroSource.MOBILE) is None
