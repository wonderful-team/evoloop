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
from app.core.learning.macro import (
    VOICE_POLICY,
    WEB_POLICY,
    MacroEngine,
    MacroRunResult,
    get_navigation_info,
    load_macro,
    resolve_project_base_url,
)
from app.core.routing.routing_data import get_store

logger = logging.getLogger(__name__)

_routing_store = get_store()


@dataclass
class ActionOutcome:
    """Result of executing a routed local/macro action."""

    ok: bool
    message: str
    action_type: str  # macro | navigate | local
    data: dict[str, Any] = field(default_factory=dict)


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
    responses = _routing_store.responses

    macro = await load_macro(macro_id)
    if macro is None:
        return ActionOutcome(False, responses["macro"]["not_found"], "macro", {})

    # Navigation macros are a special case: they don't run, they just redirect.
    nav_info = get_navigation_info(macro)
    if nav_info is not None:
        route, feedback = nav_info
        return ActionOutcome(
            True, feedback, "navigate", {"route": route, "feedback": feedback}
        )

    # Inject project url as base_url for {{base_url}} substitutions (L0 path
    # runs run_deterministic directly; base_url must be resolved here).
    if "base_url" not in args:
        base_url = await resolve_project_base_url(macro.project_id)
        if base_url:
            args["base_url"] = base_url

    policy = VOICE_POLICY if source == "voice" else WEB_POLICY

    async def _run() -> MacroRunResult:
        return await MacroEngine.run(
            thread_id,
            macro,
            params=args,
            project_id=project_id,
            policy=policy,
            skip_activity_log=True,
            skip_recording=True,
        )

    task = asyncio.create_task(_run())
    await registry.register_worker(thread_id, task, description=f"macro:{macro_id}")

    try:
        if timeout is not None:
            result = await asyncio.wait_for(task, timeout=timeout)
        else:
            result = await task
    except asyncio.TimeoutError:
        return ActionOutcome(False, responses["macro"]["timeout"], "macro", {})
    except asyncio.CancelledError:
        # Propagate cancellation so the channel adapter can clean up.
        raise

    return ActionOutcome(
        bool(result.success),
        result.message
        or (
            responses["macro"]["success"]
            if result.success
            else responses["macro"]["failure"]
        ),
        "macro",
        {
            "fell_back": result.status == "fallback_required",
            "macro_id": macro_id,
            "macro_name": macro.name,
            "failure": result.message if not result.success else "",
        },
    )
