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

from app.core.rewind.events import (
    RewindEventType,
    RewindRequestedEvent,
    StateResetEvent,
)
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe
from app.core.globals import get_graph

if TYPE_CHECKING:
    from app.core.rewind.events import RewindRequestedEvent

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
        
        This discovers the appropriate checkpoint and rolls back state.
        """
        if not event.reset_state:
            logger.debug("[StateRewind] State reset disabled, skipping")
            return

        try:
            # Get the target human sequence
            target_sequence = await self._get_target_human_sequence(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )

            # Perform checkpoint rollback
            checkpoint_id = await self._rollback_to_checkpoint(
                thread_id=event.thread_id,
                target_human_sequence=target_sequence,
                reset_state=event.reset_state
            )

            self._last_checkpoint_id = checkpoint_id

            if checkpoint_id:
                logger.info(f"[StateRewind] Rolled back to checkpoint {checkpoint_id}")
            else:
                logger.warning("[StateRewind] No matching checkpoint found")

        except Exception as e:
            logger.error(f"[StateRewind] State rollback failed: {e}")
            raise

    @event_subscribe(RewindEventType.STATE_RESET)
    async def _handle_state_reset(self, event: StateResetEvent) -> None:
        """
        Handle specific state reset event.
        
        This performs direct state reset operations.
        """
        try:
            await self._reset_state(
                thread_id=event.thread_id,
                checkpoint_id=event.checkpoint_id,
                reset_blackboard=event.reset_blackboard,
                reset_iteration_count=event.reset_iteration_count
            )
            logger.info(f"[StateRewind] Reset state for thread {event.thread_id}")
        except Exception as e:
            logger.error(f"[StateRewind] State reset failed: {e}")
            raise

    async def _get_target_human_sequence(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """
        Get the human message sequence up to the target.
        
        Args:
            thread_id: The thread ID
            target_message_id: The target message (None = last human)
            include_target: Whether to include the target
            
        Returns:
            List of human message contents
        """
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message

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

    async def _rollback_to_checkpoint(
        self,
        thread_id: str,
        target_human_sequence: list[str],
        reset_state: bool
    ) -> str | None:
        """
        Rollback LangGraph to the checkpoint matching the target sequence.
        
        Args:
            thread_id: The thread ID
            target_human_sequence: List of human message contents
            reset_state: Whether to reset blackboard/iteration
            
        Returns:
            The checkpoint ID after rollback, or None if not found
        """
        graph = get_graph()
        if not graph:
            logger.warning("[StateRewind] Graph not available")
            return None

        config = {"configurable": {"thread_id": thread_id}}

        # Get target sequence text
        target_seq_text = [self._extract_text(c) for c in target_human_sequence]
        target_joined = "".join(target_seq_text).replace("\n", "").replace(" ", "")

        logger.info(f"[StateRewind] Looking for checkpoint matching sequence: {target_joined[:100]}...")

        # Search through checkpoint history
        historical_states = []
        try:
            async for state_snapshot in graph.aget_state_history(config):
                historical_states.append(state_snapshot)
        except Exception as e:
            logger.warning(f"[StateRewind] Failed to get state history: {e}")
            return None

        # Find matching sequence (search from newest to oldest)
        checkpoint_id = None
        base_state = None
        graph_updates = []

        for state_snapshot in historical_states:
            sn_msgs = state_snapshot.values.get("messages", []) if state_snapshot.values else []
            sn_human_seq = [self._extract_text(m.content) for m in sn_msgs if isinstance(m, HumanMessage)]
            sn_joined = "".join(sn_human_seq).replace("\n", "").replace(" ", "")

            if sn_joined == target_joined:
                checkpoint_id = state_snapshot.config["configurable"].get("checkpoint_id")
                base_state = state_snapshot

                logger.info(f"[StateRewind] Found matching checkpoint: {checkpoint_id}")

                # Mark stale messages for removal
                found_target_human = False
                for m in sn_msgs:
                    if isinstance(m, HumanMessage) and self._extract_text(m.content) == target_seq_text[-1]:
                        found_target_human = True
                        continue
                    if found_target_human and isinstance(m, (AIMessage, ToolMessage)):
                        graph_updates.append(RemoveMessage(id=m.id))

                break

        # Fallback: prefix matching for edited messages
        if not checkpoint_id and len(target_seq_text) > 0:
            logger.warning("[StateRewind] Full sequence match failed, trying prefix match...")
            prefix_seq_text = target_seq_text[:-1]
            prefix_joined = "".join(prefix_seq_text).replace("\n", "").replace(" ", "")

            for state_snapshot in historical_states:
                sn_msgs = state_snapshot.values.get("messages", []) if state_snapshot.values else []
                sn_human_seq = [self._extract_text(m.content) for m in sn_msgs if isinstance(m, HumanMessage)]
                sn_joined = "".join(sn_human_seq).replace("\n", "").replace(" ", "")

                if sn_joined == prefix_joined:
                    checkpoint_id = state_snapshot.config["configurable"].get("checkpoint_id")
                    base_state = state_snapshot
                    logger.info(f"[StateRewind] Found prefix match at checkpoint: {checkpoint_id}")
                    break

        # Update state if checkpoint found
        if checkpoint_id and base_state:
            updates = {}
            if graph_updates:
                updates["messages"] = graph_updates

            if reset_state:
                # Reset blackboard
                new_bb = base_state.values.get("blackboard", {}).copy()
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
                updated_config = await graph.aupdate_state(base_state.config, updates)
                if updated_config and "configurable" in updated_config:
                    new_checkpoint_id = updated_config["configurable"].get("checkpoint_id")
                    if new_checkpoint_id:
                        logger.info(f"[StateRewind] State updated to new checkpoint: {new_checkpoint_id}")
                        return new_checkpoint_id
            except Exception as e:
                logger.error(f"[StateRewind] Failed to update state: {e}")

        return checkpoint_id

    async def _reset_state(
        self,
        thread_id: str,
        checkpoint_id: str | None,
        reset_blackboard: bool,
        reset_iteration_count: bool
    ) -> None:
        """
        Reset specific state fields.
        
        This is a more targeted state reset than full checkpoint rollback.
        """
        # Implementation would be similar to _rollback_to_checkpoint
        # but focused on resetting specific fields
        logger.debug(f"[StateRewind] Reset state for thread {thread_id}")

    def _extract_text(self, content) -> str:
        """Extract text from various content formats."""
        if not content:
            return ""

        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8")

        # Handle Stringified JSON/Dict
        if isinstance(content, str):
            content = content.strip()
            if (content.startswith("{") and content.endswith("}")) or \
               (content.startswith("[") and content.endswith("]")):
                try:
                    parsed = json.loads(content)
                    return self._extract_text(parsed)
                except:
                    try:
                        import ast
                        parsed = ast.literal_eval(content)
                        return self._extract_text(parsed)
                    except:
                        text_matches = re.findall(r'["\']text["\']:\s*["\'](.*?)["\']', content)
                        if text_matches:
                            return "".join(text_matches).strip()
            return content

        # Handle List
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict):
                    texts.append(item.get("text", ""))
                elif isinstance(item, str):
                    texts.append(item)
            return "".join(texts).strip()

        # Handle Dict
        if isinstance(content, dict):
            return content.get("text", "") or content.get("content", "") or str(content)

        return str(content).strip()

    def get_last_checkpoint_id(self) -> str | None:
        """Get the checkpoint ID from the last rollback operation."""
        return self._last_checkpoint_id
