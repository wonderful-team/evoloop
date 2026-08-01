import pytest

from app.core.execution.macro.engine import MacroEngine
from app.core.execution.macro.schemas import MacroScript, MacroStep


@pytest.mark.asyncio
async def test_bash_step_captures_stdout():
    """A bash step should capture stdout and store it under the requested key."""
    script = MacroScript(
        steps=[
            MacroStep(
                step_number=1,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "echo 'hello devices'", "key": "greeting"},
            )
        ]
    )
    extracted = {}
    ok, msg, _fallback = await MacroEngine.execute(
        thread_id="test-bash-1",
        script=script,
        extracted_data=extracted,
    )
    assert ok is True
    assert extracted.get("greeting") == "hello devices"


@pytest.mark.asyncio
async def test_bash_step_multiple_outputs():
    """Multiple bash steps should populate distinct keys."""
    script = MacroScript(
        steps=[
            MacroStep(
                step_number=1,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "printf 'agents'", "key": "online_agents"},
            ),
            MacroStep(
                step_number=2,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "printf 'mobile'", "key": "mobile_devices"},
            ),
            MacroStep(
                step_number=3,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "printf 'network'", "key": "local_network"},
            ),
        ]
    )
    extracted = {}
    ok, msg, _fallback = await MacroEngine.execute(
        thread_id="test-bash-2",
        script=script,
        extracted_data=extracted,
    )
    assert ok is True
    assert extracted == {
        "online_agents": "agents",
        "mobile_devices": "mobile",
        "local_network": "network",
    }


@pytest.mark.asyncio
async def test_bash_step_failure_continues_on_error():
    """A failing bash step with continue_on_error should store the error and continue."""
    script = MacroScript(
        steps=[
            MacroStep(
                step_number=1,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "false", "key": "fail", "continue_on_error": True},
            ),
            MacroStep(
                step_number=2,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "echo 'ok'", "key": "ok"},
            ),
        ]
    )
    extracted = {}
    ok, msg, _fallback = await MacroEngine.execute(
        thread_id="test-bash-3",
        script=script,
        extracted_data=extracted,
    )
    assert ok is True
    assert "Exit code 1" in extracted.get("fail", "")
    assert extracted.get("ok") == "ok"


@pytest.mark.asyncio
async def test_bash_step_failure_raises_by_default():
    """A failing bash step without continue_on_error should fail the macro."""
    script = MacroScript(
        steps=[
            MacroStep(
                step_number=1,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "false", "key": "fail"},
            ),
        ]
    )
    ok, msg, _fallback = await MacroEngine.execute(
        thread_id="test-bash-4",
        script=script,
    )
    assert ok is False
    assert "Exit code 1" in msg


@pytest.mark.asyncio
async def test_bash_step_timeout():
    """A bash step that exceeds its timeout should fail."""
    script = MacroScript(
        steps=[
            MacroStep(
                step_number=1,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"command": "sleep 5", "key": "slow", "timeout": 0.5},
            ),
        ]
    )
    ok, msg, _fallback = await MacroEngine.execute(
        thread_id="test-bash-5",
        script=script,
    )
    assert ok is False
    assert "timed out" in msg.lower()


@pytest.mark.asyncio
async def test_bash_step_missing_command():
    """A bash step without a command should fail the macro."""
    script = MacroScript(
        steps=[
            MacroStep(
                step_number=1,
                type="bash",
                event_type="bash",
                source="desktop",
                payload={"key": "missing"},
            ),
        ]
    )
    ok, msg, _fallback = await MacroEngine.execute(
        thread_id="test-bash-6",
        script=script,
    )
    assert ok is False
    assert "command" in msg.lower()


def test_discover_connected_devices_macro_script():
    """The seeded discover_connected_devices macro must parse as bash steps."""
    from scripts.seed_global_macros import MACROS
    from app.utils.yaml import macro_from_yaml

    macro = next(m for m in MACROS if m["name"] == "discover_connected_devices")
    steps = macro_from_yaml(macro["macro_script"])
    script = MacroScript(steps=steps)
    assert len(script.steps) == 3
    keys = [s.payload.key for s in script.steps]
    assert keys == ["online_agents", "mobile_devices", "local_network"]
    for step in script.steps:
        assert step.type == "bash"
        assert step.payload.continue_on_error is True
