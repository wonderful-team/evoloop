"""
State Rewind Handler
====================

Handles LangGraph state and checkpoint rollback when conversation is rewound.

This module provides event-driven state management for the rewind system,
including checkpoint discovery, state reset, and blackboard cleanup.
"""

import json
import logging
import re
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, RemoveMessage
from sqlalchemy import select

from app.core.engine.rewind.events import RewindEventType, RewindRequestedEvent
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe
from app.core.globals import get_graph
from app.infrastructure.database.sql.database import session_scope
from app.models import Message

if TYPE_CHECKING:
    from app.core.engine.rewind.events import RewindRequestedEvent

logger = logging.getLogger(__name__)


@event_register()
class StateRewind:
    """
    Handles LangGraph state rollback when conversation is rewound.
    
    This handler subscribes to rewind events and:
    1. Discovers the appropriate checkpoint for the target state
    2. Rolls back the LangGraph state to that checkpoint
    3. Resets blackboard and iteration count if requested
    
    Usage:
        StateRewind.register(system_bus)
    """

    def __init__(self):
        self._last_checkpoint_id: str | None = None

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "StateRewind":
        """
        Register this handler to the event bus.
        
        Args:
            bus: The event bus to subscribe to
            
        Returns:
            The handler instance
        """
        instance = cls()
        from app.core.events.decorators import register_instance_handlers
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - perform checkpoint rollback.
        
        For retry operations, finds the oldest clean checkpoint and resets state.
        For targeted rewind, rolls back to the checkpoint matching the target message.
        """
        # Perform checkpoint rollback
        checkpoint_id = await self._rollback_to_checkpoint(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            reset_state=event.reset_state,
            include_target=event.include_target,
            reason=event.reason
        )

        self._last_checkpoint_id = checkpoint_id

        if checkpoint_id:
            event.results["checkpoint_id"] = checkpoint_id
            logger.info(f"[StateRewind] Rolled back to checkpoint {checkpoint_id}")
        else:
            logger.warning("[StateRewind] No matching checkpoint found")

    async def _rollback_to_checkpoint(
        self,
        thread_id: str,
        target_message_id: str | None,
        reset_state: bool,
        include_target: bool = True,
        reason: str = "user_request"
    ) -> str | None:
        """
        Rollback LangGraph to the appropriate checkpoint.
        
        For retry: finds the oldest 'input' checkpoint and prunes all polluted messages.
        For targeted rewind: attempts to find the checkpoint closest to the target message.
        
        Args:
            thread_id: The thread ID
            target_message_id: The target message (None = last human)
            reset_state: Whether to reset blackboard/iteration
            reason: Why the rewind was triggered
            
        Returns:
            The checkpoint ID after rollback, or None if not found
        """
        graph = get_graph()
        if not graph:
            logger.warning("[StateRewind] Graph not available")
            return None

        config = {"configurable": {"thread_id": thread_id}}

        # Search through checkpoint history (newest first)
        historical_states = []
        try:
            async for state_snapshot in graph.aget_state_history(config):
                historical_states.append(state_snapshot)
        except Exception as e:
            logger.warning(f"[StateRewind] Failed to get state history: {e}")
            return None

        if not historical_states:
            logger.warning("[StateRewind] No checkpoint history found")
            return None

        checkpoint_id = None
        base_state = None
        graph_updates = []

        # ------------------------------------------------------------------
        # Unified strategy: Find checkpoint containing target message,
        # remove target and all messages after it, keep everything before.
        # For retry (include_target=False), the target human message itself
        # is kept; only messages after it are removed.
        # ------------------------------------------------------------------
        target_sequence = await self._get_target_human_sequence(
            thread_id=thread_id,
            target_message_id=target_message_id,
            include_target=True
        )

        if not target_sequence:
            logger.warning("[StateRewind] No target sequence found")
            return None

        target_anchor = self._normalize_for_match(self._extract_text(target_sequence[-1]))

        found_target = False
        for state_snapshot in historical_states:
            sn_msgs = state_snapshot.values.get("messages", []) if state_snapshot.values else []

            for m in sn_msgs:
                if isinstance(m, HumanMessage) and target_anchor:
                    msg_text = self._normalize_for_match(self._extract_text(m.content))
                    if msg_text == target_anchor:
                        found_target = True
                        if include_target:
                            graph_updates.append(RemoveMessage(id=m.id))
                        continue

                if found_target:
                    graph_updates.append(RemoveMessage(id=m.id))

            if found_target:
                checkpoint_id = state_snapshot.config.get("configurable", {}).get("checkpoint_id")
                base_state = state_snapshot
                logger.info(
                    f"[StateRewind] Found checkpoint {checkpoint_id} with target, "
                    f"removing {len(graph_updates)} messages (after target, include_target={include_target})"
                )
                break

        if not found_target:
            latest = historical_states[0]
            checkpoint_id = latest.config.get("configurable", {}).get("checkpoint_id")
            base_state = latest
            sn_msgs = base_state.values.get("messages", []) if base_state.values else []

            last_human_idx = -1
            for i, m in enumerate(sn_msgs):
                if isinstance(m, HumanMessage):
                    last_human_idx = i

            if last_human_idx >= 0:
                for m in sn_msgs[last_human_idx:]:
                    graph_updates.append(RemoveMessage(id=m.id))

            logger.info(
                f"[StateRewind] Target not found in checkpoints, using latest {checkpoint_id}. "
                f"Removing {len(graph_updates)} messages from last human onward."
            )

        # ------------------------------------------------------------------
        # Apply updates
        # ------------------------------------------------------------------
        if checkpoint_id and base_state:
            updates = {}
            if graph_updates:
                updates["messages"] = graph_updates

            if reset_state:
                # Reset blackboard turn keys
                new_bb = base_state.values.get("blackboard", {}).copy() if base_state.values else {}
                turn_keys_to_reset = [
                    "ticket", "verification", "route_reason", "next_node",
                    "situation_analysis", "action_plan", "error", "spawn_plan",
                    "pending_aggregation", "plan_approved"
                ]
                for key in turn_keys_to_reset:
                    new_bb[key] = None

                updates.update({
                    "blackboard": new_bb,
                    "iteration_count": 0,
                    "current_plan": None,
                    "structured_plan": None,
                    "next_node": None,
                    "situation_analysis": None,
                    "action_plan": None,
                    "error": None
                })

            try:
                updated_config = await graph.aupdate_state(base_state.config, updates, as_node="__start__")
                if updated_config and "configurable" in updated_config:
                    new_checkpoint_id = updated_config["configurable"].get("checkpoint_id")
                    if new_checkpoint_id:
                        logger.info(f"[StateRewind] State updated to new checkpoint: {new_checkpoint_id}")
                        return new_checkpoint_id
            except Exception as e:
                logger.error(f"[StateRewind] Failed to update state: {e}")

        return checkpoint_id

    async def _get_target_human_sequence(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """
        Get the human message sequence up to the target from the DB.
        
        Args:
            thread_id: The thread ID
            target_message_id: The target message (None = last human)
            include_target: Whether to include the target
            
        Returns:
            List of human message contents
        """
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(Message.thread_id == thread_id)
                .where(Message.role == "human")
                .order_by(Message.id.asc())
            )

            if target_message_id:
                target_id = int(target_message_id)
                if include_target:
                    stmt = stmt.where(Message.id <= target_id)
                else:
                    stmt = stmt.where(Message.id < target_id)

            result = await session.execute(stmt)
            messages = result.scalars().all()

            return [self._extract_text(m.content) for m in messages]

    def _extract_text(self, content) -> str:
        """Extract text from various content formats."""
        if not content:
            return ""

        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8")

        # Recursive extraction for nested data structures
        if isinstance(content, list):
            return "".join([self._extract_text(item) for item in content])

        if isinstance(content, dict):
            # Try specific keys in order of likelihood
            for key in ["text", "content", "reasoning", "thought"]:
                if key in content:
                    return self._extract_text(content[key])
            # Fallback: join all string values
            return "".join([str(v) for v in content.values() if isinstance(v, (str, list, dict))])

        if isinstance(content, str):
            content = content.strip()
            if (content.startswith("{") and content.endswith("}")) or \
               (content.startswith("[") and content.endswith("]")):
                try:
                    parsed = json.loads(content)
                    return self._extract_text(parsed)
                except:
                    # If JSON parsing fails, use regex as a fallback to grab anything in 'text' fields
                    text_matches = re.findall(r'["\']text["\']:\s*["\'](.*?)["\']', content)
                    if text_matches:
                        return "".join(text_matches).strip()
            return content

    def _normalize_for_match(self, text: str) -> str:
        """Final normalization for sequence comparison."""
        if not text:
            return ""
        # Remove ALL whitespace, system tags, and common delimiters to get a pure 'fingerprint'
        text = re.sub(r'\[CONTEXT UPDATE.*?\]', '', text) # Remove system injection noise
        text = re.sub(r'[\s\n\r\t.,!?;:()\[\]{}"\']+', '', text)
        return text.lower()

    def get_last_checkpoint_id(self) -> str | None:
        """Get the checkpoint ID from the last rollback operation."""
        return self._last_checkpoint_id
