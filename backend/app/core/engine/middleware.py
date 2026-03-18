import logging
import uuid
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
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
        blackboard = state.get("blackboard") or {}
        
        # If we are in a fresh run, context was lost, or this is an isolated subtask
        if ctx.request_id == "global-fallback" or state.get("is_subtask"):
            project_id = state.get("project_id")
            if project_id is None:
                project_id = config.get("configurable", {}).get("project_id", DEFAULT_PROJECT_ID)

            working_directory = (
                blackboard.get("working_directory") or 
                config.get("configurable", {}).get("working_directory")
            )
            # [Phase 5] Prioritize state's thread_id (for subtask isolation)
            thread_id = state.get("thread_id") or config.get("configurable", {}).get("thread_id")

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

        if last_human_msg and settings.USE_NEO4J_MEMORY and not state.get("is_subtask"):
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
        if not blackboard.get("verification") and state.get("verification_status"):
            blackboard["verification"] = state.get("verification_status")

        # 4b. Metadata Reset (Industrial Hardening)
        # Clear terminal status markers from previous runs to prevent misaligned prompts on retry
        is_retry = config.get("metadata", {}).get("is_retry", False)
        
        if (state.get("is_retry") or is_retry) and not state.get("is_subtask"):
             logger.info("[Middleware] 🔄 Retry detected: Performing deep blackboard cleanup.")
             for key in ["ticket", "verification", "route_reason"]:
                 blackboard[key] = None
             
             if "metadata" in blackboard:
                 for key in ["final_outcome", "shadow_audit"]:
                     if key in blackboard["metadata"]:
                         del blackboard["metadata"][key]
        elif "metadata" in blackboard and not state.get("is_subtask"):
            for key in ["final_outcome", "shadow_audit"]:
                if key in blackboard["metadata"]:
                    logger.debug(f"[Middleware] Resetting terminal metadata '{key}' for new run.")
                    del blackboard["metadata"][key]

        state["blackboard"] = blackboard
        return state
