"""Macro sedimentation service — flywheel macro creation from completed traces.

This module owns the automatic creation of ``Macro`` records when a session is
marked as sedimentation-eligible by ``FinishNode``. It is intentionally separate
from skill synthesis: only the macro is persisted; any companion skill is the
responsibility of explicit synthesis flows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.config import settings
from app.core.execution.macro.compiler import ALLOWED_UI_ACTIONS
from app.infrastructure.database import session_scope
from app.models import AgentActivity, Message, TraceEvent

if TYPE_CHECKING:
    from app.models.macro import Macro

logger = logging.getLogger(__name__)

# Raw mobile mirror events that MacroScriptCompiler normalizes into macro actions.
_RAW_MOBILE_EVENT_TYPES = frozenset({
    "touch_down",
    "touch_up",
    "mouse_click",
    "swipe",
    "key",
})

# Event types that can be turned into deterministic macro steps. Kept in sync
# with the compiler's ALLOWED_UI_ACTIONS so eligibility checks do not promise a
# macro that the compiler cannot produce.
_REPLAYABLE_EVENT_TYPES = ALLOWED_UI_ACTIONS | _RAW_MOBILE_EVENT_TYPES

_EXCLUDED_EVENT_TYPES = frozenset({
    "llm_output",
    "tool_result",
    "node_start",
    "macro_thought",
    "list_macros",
    "list_skills",
    "search_history",
    "recall",
    "read_file",
    "list_dir",
    "grep_search",
    "find_files",
    "ask_human",
    "ask_confirm",
    "forget_tool_outputs",
    "think",
})


class MacroSedimentationService:
    """Service for determining eligibility and creating macros from traces."""

    @staticmethod
    async def is_eligible(thread_id: str) -> bool:
        """Return True if the thread contains at least one replayable deterministic step.

        The check filters out deleted messages, exploratory events, and failure
        signals without invoking the LLM or the full compiler.
        """
        try:
            async with session_scope() as session:
                msg_stmt = select(Message.id).where(Message.thread_id == thread_id)
                msg_result = await session.execute(msg_stmt)
                existing_message_ids = set(msg_result.scalars().all())

                stmt = select(TraceEvent).where(TraceEvent.thread_id == thread_id)
                result = await session.execute(stmt)
                for event in result.scalars().all():
                    if MacroSedimentationService._is_replayable(event, existing_message_ids):
                        return True
                return False
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.warning(
                "[MacroSedimentation] Failed to check eligibility for %s: %s",
                thread_id,
                e,
            )
            return False

    @staticmethod
    def _is_replayable(event: TraceEvent, existing_message_ids: set[str]) -> bool:
        """Evaluate a single trace event for replayability."""
        if event.message_id is not None and event.message_id not in existing_message_ids:
            return False

        event_type = event.event_type
        if event_type is None or event_type in _EXCLUDED_EVENT_TYPES:
            return False

        payload = event.payload or {}
        if event.reward is not None and event.reward < 0:
            return False
        if payload.get("success") is False:
            return False

        if event_type in _REPLAYABLE_EVENT_TYPES:
            return True

        # Tool calls may wrap a replayable UI action in their payload.
        if event_type == "tool_call":
            tool_name = payload.get("name")
            args = payload.get("args") or {}
            if isinstance(args, dict):
                inner_action = args.get("action")
                if inner_action in _REPLAYABLE_EVENT_TYPES:
                    return True
            if tool_name in _REPLAYABLE_EVENT_TYPES:
                return True

        return False

    @staticmethod
    async def sediment(thread_id: str, member_id: int = 0) -> Macro | None:
        """Create a pending_review macro from a completed, eligible trace.

        Returns the created macro or None if the feature is disabled, the thread
        is not eligible, or the trace does not produce any deterministic steps.
        """
        if not settings.AUTO_MACRO_SEDIMENTATION_ENABLED:
            logger.debug("[MacroSedimentation] Disabled for %s", thread_id)
            return None

        try:
            async with session_scope() as session:
                activity = await session.get(AgentActivity, thread_id)
                if activity is None:
                    return None
                if activity.final_outcome.upper() != "COMPLETED":
                    return None
                if not activity.sedimentation_eligible:
                    return None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.warning(
                "[MacroSedimentation] Failed to read AgentActivity for %s: %s",
                thread_id,
                e,
            )
            return None

        try:
            from app.core.execution.macro.compiler import MacroScriptCompiler
            from app.core.execution.macro.lifecycle import create_macro_from_synthesis
            from app.core.learning.trace_parser import TraceParser
            from app.core.learning.workflow_synthesizer import WorkflowSynthesizer
            from app.utils.parameters import normalize_parameters

            sequence = await TraceParser(thread_id).parse()
            if not sequence.steps:
                logger.info("[MacroSedimentation] No trace steps for %s; skipping", thread_id)
                return None

            compiled = MacroScriptCompiler().compile(sequence)
            if not compiled.steps:
                logger.info(
                    "[MacroSedimentation] Trace for %s produced no deterministic steps; skipping",
                    thread_id,
                )
                return None

            macro_script = compiled.to_yaml()

            synthesizer = WorkflowSynthesizer(
                thread_id, sequence=sequence, macro_script=macro_script, mode="macro"
            )
            synthesis_result = await synthesizer.synthesize()
            macro_metadata = synthesis_result.macro
            if macro_metadata is None:
                raise ValueError("Macro synthesis did not produce macro metadata")

            async with session_scope() as db:
                macro = await create_macro_from_synthesis(
                    db,
                    name=macro_metadata.name,
                    description=macro_metadata.description,
                    trigger_patterns=macro_metadata.trigger_patterns,
                    parameters=normalize_parameters(macro_metadata.parameters),
                    macro_script=macro_script,
                    namespace=macro_metadata.namespace,
                    source_thread_id=thread_id,
                    project_id=None,
                    member_id=member_id,
                )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.error(
                "[MacroSedimentation] Failed to sediment macro for %s: %s",
                thread_id,
                e,
            )
            return None

        try:
            from app.core.events.publishers import publish_macro_mutated

            await publish_macro_mutated(macro.id, action="create")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.warning(
                "[MacroSedimentation] Failed to publish macro mutated for %s: %s",
                thread_id,
                e,
            )
        return macro
