import json
import logging
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from sqlalchemy import select

from app.core.memory import memory_manager
from app.infrastructure.database.sql.database import session_scope
from app.models import TraceEvent

logger = logging.getLogger(__name__)


class TraceCallbackHandler(AsyncCallbackHandler):
    """
    Recorder for Imitation Learning.
    Captures:
    1. Node Entry (State)
    2. Tool Usage (Action)
    3. User Intervention (Correction)
    """

    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.step_counter = 0
        self.current_node = "unknown"
        self._last_state_snapshot = {}

    async def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], **kwargs: Any
    ) -> None:
        """Capture State Snapshot on Node Entry."""
        metadata = kwargs.get("metadata", {})
        node_name = metadata.get("langgraph_node")

        if node_name:
            self.current_node = node_name
            self.step_counter += 1

            # Sanitize inputs (remove huge contexts if necessary, but we want full state for learning)
            # Serialize for DB
            try:
                # inputs might contain non-serializable objects.
                # For LangGraph, inputs IS the State (dict).
                snapshot = self._sanitize_snapshot(inputs)
                self._last_state_snapshot = snapshot

                await self._save_event(
                    action_type="node_start",
                    payload={"node": node_name},
                    snapshot=snapshot,
                )
            except Exception as e:
                logger.error(f"Failed to record node start: {e}")

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Capture Tool Output as Environment Feedback."""
        tool_name = kwargs.get("name", "unknown_tool")
        # Truncate long outputs to keep DB size manageable
        truncated_output = output[:2000] if output else ""

        await self._save_event(
            action_type="tool_result",
            payload={
                "name": tool_name,
                "output": truncated_output,
                "success": True,
            },
            snapshot=self._last_state_snapshot,
        )

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Capture Tool Usage (The Agent's Action)."""
        tool_name = serialized.get("name")
        try:
            args = json.loads(input_str)
        except Exception:
            args = {"raw": input_str}

        await self._save_event(
            action_type="tool_call",
            payload={"name": tool_name, "args": args},
            snapshot=self._last_state_snapshot,  # Action conditioned on LAST seen state
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Capture LLM Output (Thoughts/Decisions)."""
        if not response.generations:
            return

        gen = response.generations[0][0]
        content = gen.text

        await self._save_event(
            action_type="llm_output",
            payload={"content": content},
            snapshot=self._last_state_snapshot,
        )

    async def _save_event(self, action_type: str, payload: dict, snapshot: dict):
        try:
            async with session_scope() as session:
                event = TraceEvent(
                    thread_id=self.thread_id,
                    step_number=self.step_counter,
                    node_name=self.current_node,
                    state_snapshot=json.dumps(
                        snapshot, default=str
                    ),  # Handle datetimes
                    action_type=action_type,
                    action_payload=json.dumps(payload, default=str),
                )
                session.add(event)
        except Exception as e:
            logger.error(f"Failed to save trace event: {e}")

    def _sanitize_snapshot(self, state: Any) -> dict:
        """Clean up state for storage (remove huge lists, tokens, etc)."""
        if not isinstance(state, dict):
            # If state is not a dict (e.g. an AIMessage or string), wrap it
            if hasattr(state, "dict"):
                try:
                    return state.dict()
                except Exception:
                    pass
            return {"raw_input": str(state)}

        clean = {}
        for k, v in state.items():
            # Filter out known huge objects if any
            if k == "messages":
                # For learning, full context is better, but DB size...
                # Let's keep it full for now, we can prune later.
                pass
            clean[k] = v
        return clean


async def sync_thread_to_graph(
    thread_id: str,
    project_id: int,
    goal: str = None,
    result_summary: str = None,
    concept_names: list[str] = None,
    source_message_id: str = None,
):
    """
    Syncs the completed thread's trace from SQL to Neo4j as an Episode.
    This creates the 'Episodic Memory'.

    Args:
        thread_id: The conversation thread ID
        project_id: Project context
        goal: User's original goal (from first HumanMessage)
        result_summary: Session summary from SessionConclusion
        concept_names: List of harvested concept names to link
        source_message_id: ID of the final response message
    """
    # 1. Fetch Trace (for fallback extraction if params not provided)
    events = []
    async with session_scope() as session:
        stmt = (
            select(TraceEvent)
            .where(TraceEvent.thread_id == thread_id)
            .order_by(TraceEvent.step_number)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

    if not events:
        logger.warning(
            f"No trace events found for thread {thread_id}, skipping graph sync."
        )
        return

    # 2. Extract/Fallback Metadata
    final_goal = goal or "Unknown Task"
    final_result = result_summary or "Completed"
    error = None
    plan_snapshot = "No plan recorded"

    # Fallback: If goal not provided, try to extract from first event
    if not goal:
        try:
            first_event = events[0]
            snapshot = json.loads(first_event.state_snapshot)
            msgs = snapshot.get("messages", [])
            if msgs and isinstance(msgs[0], dict) and msgs[0].get("type") == "human":
                final_goal = msgs[0].get("content", "Unknown Task")
        except Exception:
            pass

    # Determine success/failure from last node
    last_event = events[-1]
    if last_event.node_name != "finish":
        error = f"Ended at {last_event.node_name} instead of finish"

    # Extract Plan from state snapshots
    for e in reversed(events):
        try:
            snap = json.loads(e.state_snapshot)
            if snap.get("current_plan"):
                plan_snapshot = snap.get("current_plan")
                break
        except Exception:
            continue

    # 3. Store Episode to Graph
    from app.core.memory.interfaces.long_term import Episode
    episode = Episode(
        final_goal[:2000],
        final_result[:2000] if final_result else "Success",
        plan_snapshot[:5000],
        error,
        project_id,
        source_message_id,
    )
    episode_id = await memory_manager.long_term.record_episode(episode)

    # 4. Link Episode to Concepts (NEW)
    if concept_names and episode_id:
        try:
            await memory_manager.long_term.link_episode_to_concepts(
                episode_id=episode_id,
                concept_names=concept_names,
                project_id=project_id
            )
            logger.info(f"Linked Episode {episode_id} to {len(concept_names)} concepts")
        except Exception as e:
            logger.warning(f"Failed to link Episode to Concepts: {e}")
