"""Macro compilation from trace sequences.

This module lives in the macro execution domain and converts structured trace
steps into a deterministic MacroScript. It is intentionally decoupled from
skill synthesis, which only produces metadata (name, description, triggers,
parameters).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from app.core.learning.constants import ALLOWED_UI_ACTIONS
from app.core.learning.macro.schemas import (
    ExtractType,
    MacroActionType,
    MacroScript,
    MacroSource,
    MacroStep,
    MacroStepType,
)
from app.core.learning.macro.utils import cleanup_macro_steps

import app.core.learning.constants as _mc

if TYPE_CHECKING:
    from app.core.learning.schemas.migrated import TraceStep
    from app.core.learning.trace.parser import TraceSequence

logger = logging.getLogger(__name__)


# Trace action names that pass ALLOWED_UI_ACTIONS but are not MacroActionType
# members — remap before constructing MacroStep (enum-validated).
_EVENT_TYPE_REMAP = {
    _mc.GOTO: _mc.NAVIGATE,
    _mc.INPUT_TEXT: _mc.INPUT,
    _mc.EVALUATE: _mc.RUN_JS,
    _mc.DUMP: _mc.DUMP_UI,
    _mc.EXTRACT: _mc.GET_TEXT,
}

# Raw mobile mirror events that must be normalized before macro compilation.
_RAW_MOBILE_EVENT_TYPES = frozenset(
    {
        _mc.TOUCH_DOWN,
        _mc.TOUCH_UP,
        _mc.MOUSE_CLICK,
        _mc.SWIPE,
        _mc.KEY,
    }
)


class MacroScriptCompiler:
    """Compile a TraceSequence into a deterministic MacroScript."""

    def compile(self, sequence: TraceSequence) -> MacroScript:
        """Compile raw TraceSteps into a clean structured MacroScript."""
        from app.core.learning.trace.parser import TraceSequence

        if not isinstance(sequence, TraceSequence):
            raise TypeError(
                f"MacroScriptCompiler expects TraceSequence, got {type(sequence)}"
            )

        steps = []
        has_extract = False
        last_package = None

        for step in sequence.steps:
            # Skip non-UI/agentic control events
            if step.action_type in (
                "node_start",
                "llm_output",
                "tool_result",
                "macro_thought",
            ):
                continue

            # Normalize raw mobile mirror events into macro-executable actions.
            action_type, action_args = self._normalize_action(step)
            if action_type is None:
                continue

            # Determine source
            source_type = MacroSource.DOM
            current_package = step.state_context.get("app_name") or step.node_name

            if action_type == "mobile" or step.action_name == "mobile":
                source_type = MacroSource.MOBILE
            elif (
                action_type == "desktop"
                or step.action_name == "desktop"
            ):
                source_type = MacroSource.DESKTOP
            elif step.state_context.get("source") == _mc.MOBILE:
                # Android mirror recordings (tap/swipe/key_press normalized above)
                source_type = MacroSource.MOBILE
            elif step.node_name in ("global_observation", "mobile_interaction"):
                source_type = (
                    MacroSource.MOBILE
                    if step.state_context.get("is_mirrored")
                    else MacroSource.DESKTOP
                )

            # Detect App Transition (mobile only)
            if source_type == MacroSource.MOBILE and current_package not in (
                "global_observation",
                "mobile_interaction",
                "unknown",
            ):
                if last_package and current_package != last_package:
                    system_apps = (
                        "com.android.launcher",
                        "com.android.systemui",
                        "android",
                        "scrcpy",
                    )
                    if not any(current_package.startswith(sys) for sys in system_apps):
                        logger.info(
                            "[MacroCompiler] App transition detected: %s -> %s",
                            last_package,
                            current_package,
                        )
                        steps.append(
                            MacroStep(
                                type=MacroStepType.ACTION,
                                event_type=MacroActionType.OPEN_APP,
                                source=source_type,
                                payload={"package_name": current_package},
                            )
                        )
                        steps.append(
                            MacroStep(
                                type=MacroStepType.ACTION,
                                event_type=MacroActionType.WAIT,
                                source=source_type,
                                payload={"duration_ms": 1500},
                            )
                        )

                if not any(
                    current_package.startswith(sys)
                    for sys in (
                        "com.android.launcher",
                        "com.android.systemui",
                        "android",
                    )
                ):
                    last_package = current_package

            # Filter noisy keys
            if action_type == _mc.KEY_PRESS and action_args.get("key") in (
                "Alt",
                "Shift",
                "Control",
                "Command",
                "Meta",
            ):
                continue

            event_type = action_type
            payload = dict(action_args)

            if current_package and current_package not in (
                "global_observation",
                "mobile_interaction",
                "unknown",
            ):
                payload["package_name"] = current_package

            # Tool Call Normalization
            if event_type == "tool_call":
                inner_action = payload.get("action")
                if inner_action:
                    event_type = inner_action
                    if event_type == _mc.NAVIGATE:
                        event_type = _mc.GOTO
                    elif event_type == _mc.TYPE_TEXT:
                        event_type = _mc.INPUT
                else:
                    tool_invoked = step.action_name
                    if tool_invoked == _mc.WAIT_FOR:
                        event_type = _mc.WAIT
                        payload["duration_ms"] = float(payload.get("seconds", 1)) * 1000
                    else:
                        continue

            if event_type not in ALLOWED_UI_ACTIONS:
                continue

            event_type = _EVENT_TYPE_REMAP.get(event_type, event_type)
            macro_action = MacroActionType(event_type)

            target_selector = (
                step.ui_context.element_selector if step.ui_context else None
            )

            # Map to MacroStep
            if event_type in (_mc.GET_TEXT, _mc.GET_HTML, _mc.GET_ATTRIBUTE) or (
                step.action_name == "mobile"
                and payload.get("action") == _mc.DUMP_UI
            ):
                has_extract = True
                macro_step = MacroStep(
                    type=MacroStepType.EXTRACT,
                    extract_type=ExtractType(payload.get("action") or event_type),
                    key=f"data_{step.step_number}",
                    source=source_type,
                    target_selector=payload.get("selector") or target_selector,
                    payload=payload,
                    event_type=macro_action,
                )
            else:
                macro_step = MacroStep(
                    type=MacroStepType.ACTION,
                    event_type=macro_action,
                    source=source_type,
                    target_selector=target_selector,
                    payload=payload,
                )

            steps.append(macro_step)

        if has_extract:
            steps.append(MacroStep(type=MacroStepType.DUMP))

        clean_steps = cleanup_macro_steps(
            [s.model_dump(exclude_none=True) for s in steps]
        )[0]
        return MacroScript(steps=cast(list[MacroStep], clean_steps))

    def _normalize_action(self, step: TraceStep) -> tuple[str | None, dict[str, Any]]:
        """Return normalized (action_type, action_args) or (None, {}) to drop."""
        action_type = step.action_type
        action_args = dict(step.action_args)

        if (
            step.state_context.get("source") == _mc.MOBILE
            or action_type in _RAW_MOBILE_EVENT_TYPES
        ):
            normalized = _normalize_mobile_event(action_type, action_args)
            if normalized is None:
                return None, {}
            return normalized

        return action_type, action_args


def _normalize_mobile_event(
    event_type: str, payload: dict[str, Any]
) -> tuple[str | None, dict[str, Any]] | None:
    """Normalize raw Android mirror events into macro actions.

    Returns (action_name, action_args) or None to drop the event.
    The recorder emits touch_down/touch_up boundaries plus a composed
    swipe event per gesture; a near-zero-distance swipe is a tap.
    Mirror-window clicks arrive as mouse_click with device-pixel
    coordinates (transformed client-side in GlobalRecorderManager).
    """
    if event_type in (_mc.TOUCH_DOWN, _mc.TOUCH_UP):
        return None
    if event_type == _mc.MOUSE_CLICK:
        pos = payload.get("position") or {}
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            return (_mc.TAP, {"x": pos[0], "y": pos[1]})
        args = {
            k: v
            for k, v in {"x": payload.get("x"), "y": payload.get("y")}.items()
            if v is not None
        }
        return (_mc.TAP, args)
    if event_type == _mc.SWIPE:
        x, y = payload.get("x"), payload.get("y")
        end_x = payload.get("swipe_end_x")
        end_y = payload.get("swipe_end_y")
        args = {k: v for k, v in {"x": x, "y": y}.items() if v is not None}
        if end_x is None or end_y is None or x is None or y is None:
            return (_mc.TAP, args)
        distance = ((end_x - x) ** 2 + (end_y - y) ** 2) ** 0.5
        if distance < 30:
            return (_mc.TAP, args)
        args["end_x"] = end_x
        args["end_y"] = end_y
        if payload.get("swipe_duration_ms") is not None:
            args["duration_ms"] = payload["swipe_duration_ms"]
        return (_mc.SWIPE, args)
    if event_type == _mc.KEY:
        return (_mc.KEY_PRESS, {"key": payload.get("key_code")})
    # region_extract and other annotated events pass through as-is
    return (event_type, payload)
