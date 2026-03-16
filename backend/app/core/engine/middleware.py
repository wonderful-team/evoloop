import logging
import uuid
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context import ContextManager, EvoContext
from app.infrastructure.config.service import SystemConfigService
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class EvoContextMiddleware:
    """
    Middleware for unified context and state management.
    Handles hydration of Environment, Project, and Memory before session execution.
    """

    @staticmethod
    async def hydrate(state: dict, config: RunnableConfig) -> dict:
        """
        Hydrates the EvoContext and consolidates session state.
        """
        # 1. Resolve or Create Context
        ctx = ContextManager.current()
        
        # If we are in a fresh run or context was lost, initialize it
        if ctx.request_id == "global-fallback":
            project_id = state.get("project_id")
            if project_id is None:
                project_id = config.get("configurable", {}).get("project_id", 1)

            working_directory = (
                state.get("blackboard", {}).get("working_directory") or 
                state.get("scratchpad", {}).get("working_directory") or 
                config.get("configurable", {}).get("working_directory")
            )
            thread_id = config.get("configurable", {}).get("thread_id")

            ctx = EvoContext(
                project_id=project_id,
                working_directory=working_directory,
                thread_id=thread_id,
                request_id=f"run-{gen_uuid()[:8]}"
            )
            ContextManager.set(ctx)
            logger.info(f"[Middleware] 🧪 Context Initialized: project_id={project_id}, wd={working_directory}")

        # 2. Unified Environment Hydration (Plug-in Discovery)
        from app.core.context.plugins import plugin_registry
        plugin_registry.hydrate_context(ctx)

        # 3. Collaborative Memory Hydration
        # Extract last human message for semantic search
        last_human_msg = ""
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                last_human_msg = msg.content
                break

        if last_human_msg and settings.USE_NEO4J_MEMORY:
            try:
                from app.core.memory import memory_manager
                project_id = ctx.project_id or 1
                
                # Semantic search for relevant concepts and past episodes
                concepts = await memory_manager.long_term.search_concepts(last_human_msg, project_id)
                if concepts:
                    ctx.metadata["project_concepts"] = "\n".join([f"- **{c.name}**: {c.description}" for c in concepts[:3]])
                
                # Fetch recent episodic snippets for grounding
                episodes = await memory_manager.episodic.search_episodes(last_human_msg, project_id, limit=2)
                if episodes:
                    ctx.metadata["episodic_memory_raw"] = "\n".join([e.summary for e in episodes])
            except Exception as e:
                logger.warning(f"[Middleware] Memory hydration failed: {e}")

        # 4. State Harmonization (Blackboard Pattern - Phase 4 Consolidation)
        scratchpad = state.pop("scratchpad", {})  # Force migration by removing it
        ticket = state.get("execution_ticket")
        
        blackboard = state.get("blackboard") or {
            "ticket": None,
            "verification": None,
            "route_reason": None,
            "metadata": {},
            "clipboard": [],
            "visited_nodes": [],
            "working_directory": None,
            "spawn_plan": None,
            "pending_aggregation": None,
            "subtask_results": [],
            "plan_approved": False
        }

        # Sync legacy ticket
        if not blackboard.get("ticket") and ticket:
            blackboard["ticket"] = ticket

        # Deep Migration from former scratchpad
        if scratchpad:
            blackboard["metadata"].update(scratchpad.get("metadata", {}))
            
            if "workspace_clipboard" in scratchpad:
                blackboard["clipboard"] = scratchpad["workspace_clipboard"]
            
            if "visited_nodes" in scratchpad:
                blackboard["visited_nodes"] = scratchpad["visited_nodes"]
                
            if "working_directory" in scratchpad:
                blackboard["working_directory"] = scratchpad["working_directory"]
                
            if "_spawn_plan" in scratchpad:
                blackboard["spawn_plan"] = scratchpad["_spawn_plan"]
                
            if "_pending_aggregation" in scratchpad:
                blackboard["pending_aggregation"] = scratchpad["_pending_aggregation"]
                
            if "subtask_results" in scratchpad:
                blackboard["subtask_results"] = scratchpad["subtask_results"]
                
            if "plan_approved" in scratchpad:
                blackboard["plan_approved"] = scratchpad["plan_approved"]

            if "route_reason" in scratchpad:
                blackboard["route_reason"] = scratchpad["route_reason"]

        if not blackboard.get("verification") and state.get("verification_status"):
            blackboard["verification"] = state.get("verification_status")

        state["blackboard"] = blackboard
        return state
