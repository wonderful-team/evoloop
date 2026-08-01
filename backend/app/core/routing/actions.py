"""Channel-agnostic action execution for L0 routed decisions.

Voice and web adapters both call these helpers; the only differences are the
execution policy (fast-fail vs self-healing) and how the resulting
``ActionOutcome`` is presented to the user.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.engine.worker_registry import WorkerRegistry
from app.core.engine.worker_registry import worker_registry as _worker_registry
from app.core.execution.macro.runner import (
    VOICE_POLICY,
    WEB_POLICY,
    ExecutionOutcome,
    MacroGateError,
    get_navigation_info,
    load_macro,
    preflight,
    run_deterministic,
)
from app.core.routing.routing_data import get_store
from app.core.shared_state import shared_state

logger = logging.getLogger(__name__)

_routing_store = get_store()


@dataclass
class ActionOutcome:
    """Result of executing a routed local/macro/builtin action."""

    ok: bool
    message: str
    action_type: str  # macro | builtin | navigate
    data: dict[str, Any] = field(default_factory=dict)


async def run_builtin(
    action: str,
    args: dict[str, Any],
    *,
    thread_id: str,
    worker_registry: WorkerRegistry | None = None,
) -> ActionOutcome:
    """Execute a builtin L0 action (ack, cancel, rename, end, clarify)."""
    registry = worker_registry if worker_registry is not None else _worker_registry
    responses = _routing_store.builtin_responses
    if action == "ack":
        return ActionOutcome(True, responses["builtin"]["ack"], "builtin", {})

    if action == "cancel":
        cancelled = await registry.cancel_worker(thread_id)
        if cancelled:
            return ActionOutcome(True, responses["builtin"]["cancel_success"], "builtin", {"cancelled": True})
        return ActionOutcome(True, responses["builtin"]["cancel_empty"], "builtin", {"cancelled": False})

    if action == "rename":
        name = args.get("name", "")
        if name:
            await shared_state.set("agent_name", name)
        return ActionOutcome(
            True,
            responses["builtin"]["rename"].format(name=name) if name else responses["builtin"]["rename_no_name"],
            "builtin",
            {"name": name},
        )

    if action == "end":
        return ActionOutcome(True, responses["builtin"]["end"], "builtin", {})

    if action == "clarify":
        return ActionOutcome(True, responses["builtin"]["clarify"], "builtin", {})

    return ActionOutcome(False, responses["builtin"]["unknown"].format(action=action), "builtin", {})


async def run_macro(
    macro_id: int,
    args: dict[str, Any],
    *,
    thread_id: str,
    project_id: int,
    source: str = "voice",
    timeout: float | None = None,
    worker_registry: WorkerRegistry | None = None,
) -> ActionOutcome:
    """Execute a routed macro. Returns ``ActionOutcome`` with optional navigate route."""
    registry = worker_registry if worker_registry is not None else _worker_registry
    responses = _routing_store.builtin_responses

    macro = await load_macro(macro_id)
    if macro is None:
        return ActionOutcome(False, responses["macro"]["not_found"], "macro", {})

    # Navigation macros are a special case: they don't run, they just redirect.
    nav_info = get_navigation_info(macro)
    if nav_info is not None:
        route, feedback = nav_info
        return ActionOutcome(True, feedback, "navigate", {"route": route, "feedback": feedback})

    try:
        script = preflight(macro, args)
    except MacroGateError as exc:
        return ActionOutcome(False, exc.message, "macro", {})

    policy = VOICE_POLICY if source == "voice" else WEB_POLICY

    async def _run() -> ExecutionOutcome:
        return await run_deterministic(
            macro,
            thread_id=thread_id,
            params=args,
            project_id=project_id,
            script=script,
            policy=policy,
            skip_activity_log=True,
            skip_recording=True,
        )

    task = asyncio.create_task(_run())
    await registry.register_worker(thread_id, task, description=f"macro:{macro_id}")

    try:
        if timeout is not None:
            outcome = await asyncio.wait_for(task, timeout=timeout)
        else:
            outcome = await task
    except asyncio.TimeoutError:
        return ActionOutcome(False, responses["macro"]["timeout"], "macro", {})
    except asyncio.CancelledError:
        # Propagate cancellation so the channel adapter can clean up.
        raise

    return ActionOutcome(
        bool(outcome.ok),
        outcome.message or (responses["macro"]["success"] if outcome.ok else responses["macro"]["failure"]),
        "macro",
        {"fell_back": outcome.fell_back},
    )
