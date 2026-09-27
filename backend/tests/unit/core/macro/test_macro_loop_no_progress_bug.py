"""Regression tests for loop iteration semantics.

A data-collection loop whose body does not change the page (URL or target
selector) must still run for its full max_iterations. Previously a
no-progress detector (_loop_page_signature in _control.py) falsely compared
the signature *before* the current iteration against the signature *after*
the previous iteration — which are always identical — so such loops were
stopped on the SECOND iteration. The detector was removed; these tests lock
the correct behavior.
"""

from __future__ import annotations

from app.core.learning.macro.engine import ControlMixin, LoopMixin
from app.core.learning.macro.schemas import (
    MacroCondition,
    MacroSource,
    MacroStep,
    MacroStepType,
)


class _Engine(ControlMixin, LoopMixin):
    """ControlMixin subclass with mocked loop-body and page-signature.

    execute_steps returns success without changing the page; the condition is
    always true; the page signature is constant — the realistic shape of a
    data-collection / reading loop.
    """

    iterations: list[int] = []

    @classmethod
    async def execute_steps(cls, *args, **kwargs):
        params = args[2] if len(args) > 2 else {}
        cls.iterations.append(params.get("loop_index"))
        return True, "", None

    @classmethod
    async def _evaluate_condition(cls, *args, **kwargs):
        return True

    @classmethod
    async def _loop_page_signature(cls, cond_type, selector):
        return "CONSTANT_SIG"

    @classmethod
    def _inject_params(cls, value, params):
        if not value or not params:
            return value
        for k, v in (params or {}).items():
            value = value.replace("{{" + k + "}}", str(v))
        return value


def _reset():
    _Engine.iterations = []


def _collect_loop_step(max_iterations=5) -> MacroStep:
    return MacroStep(
        type=MacroStepType.LOOP,
        source=MacroSource.DOM,
        step_number=1,
        condition=MacroCondition(type="element_exists", target_selector=".row"),
        max_iterations=max_iterations,
        steps=[
            MacroStep(
                type=MacroStepType.EXTRACT,
                source=MacroSource.DOM,
                event_type="run_js",
                extract_type="run_js",
                payload={"script": "() => JSON.stringify({n: 1})"},
                step_number=1,
            )
        ],
    )


async def test_data_collection_loop_not_stopped_by_no_progress():
    _reset()
    step = _collect_loop_step(max_iterations=5)
    ok, msg, _ = await _Engine._handle_control_flow(
        "t", step, step.payload, {}, {}, disable_ocr=True
    )
    assert ok is True
    assert len(_Engine.iterations) == 5, (
        "Data-collection loop should iterate max_iterations=5 times, "
        f"but no-progress detector stopped it after {len(_Engine.iterations)} iterations."
    )
    assert _Engine.iterations == [0, 1, 2, 3, 4]


async def test_data_collection_loop_single_iteration_ok():
    _reset()
    step = _collect_loop_step(max_iterations=1)
    ok, msg, _ = await _Engine._handle_control_flow(
        "t", step, step.payload, {}, {}, disable_ocr=True
    )
    assert ok is True
    assert len(_Engine.iterations) == 1
