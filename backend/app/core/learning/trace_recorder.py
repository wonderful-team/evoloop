
from typing import Any, Dict, List, Optional
from uuid import UUID
import json
import logging
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import TraceEvent
from datetime import datetime

logger = logging.getLogger("evoloop.learning")

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
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
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
                    snapshot=snapshot
                )
            except Exception as e:
                logger.error(f"Failed to record node start: {e}")

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Capture Tool Output as Environment Feedback."""
        # We need to know WHICH tool was called.
        # on_tool_start gives serialized info, but on_tool_end only gives output.
        # We rely on the linear execution assumption for now or look at run_id if we tracked it.
        # Simplification: Just log the output.
        
        # NOTE: We can't easily link to the specific tool call args here without tracking run_id.
        # But for Imitation Learning, we mostly care about "Start Tool" (Action) and "End Tool" (Observation).
        # We'll rely on on_tool_start for the action.
        pass

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Capture Tool Usage (The Agent's Action)."""
        tool_name = serialized.get("name")
        try:
             args = json.loads(input_str)
        except:
             args = {"raw": input_str}
             
        await self._save_event(
            action_type="tool_call",
            payload={"name": tool_name, "args": args},
            snapshot=self._last_state_snapshot # Action conditioned on LAST seen state
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
            snapshot=self._last_state_snapshot
        )

    async def _save_event(self, action_type: str, payload: dict, snapshot: dict):
        try:
            async with session_scope() as session:
                event = TraceEvent(
                    thread_id=self.thread_id,
                    step_number=self.step_counter,
                    node_name=self.current_node,
                    state_snapshot=json.dumps(snapshot, default=str), # Handle datetimes
                    action_type=action_type,
                    action_payload=json.dumps(payload, default=str)
                )
                session.add(event)
        except Exception as e:
            logger.error(f"Failed to save trace event: {e}")

    def _sanitize_snapshot(self, state: Dict) -> Dict:
        """Clean up state for storage (remove huge lists, tokens, etc)."""
        clean = {}
        for k, v in state.items():
            # Filter out known huge objects if any
            if k == "messages":
                # Maybe just keep last N messages?
                # For learning, full context is better, but DB size...
                # Let's keep it full for now, we can prune later.
                pass
            clean[k] = v
        return clean
