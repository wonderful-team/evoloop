"""
EvoContextMiddleware - Unified context hydration with Predictive Memory Loading.

This module implements the Pre-Supervisor optimization strategy:
1. Predictive Memory Loading: Semantic search results are pre-loaded in background
   during LangGraph initialization, reducing ~800ms Neo4j query to ~1ms Redis read.
2. Layered Caching: Static data (skills, telemetry) cached vs Dynamic data (blackboard) fresh.
"""

import logging
import time
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context import ContextManager, EvoContext
from app.core.engine.context_cache import LayeredContextCache
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
        Layered context hydration with caching and predictive memory loading.
        
        Optimizations:
        - Predictive Memory: Tries Redis cache first (populated by bg task in chat_endpoint)
        - Static layer (cacheable): Project concepts, skills, telemetry
        - Dynamic layer (always fresh): Blackboard, execution state, messages
        """
        start_time = time.time()
        
        # 1. Resolve or Create Context
        ctx = ContextManager.current()
        blackboard = state.get("blackboard") or {}
        
        if ctx.request_id == "global-fallback" or state.get("is_subtask"):
            project_id = state.get("project_id")
            if project_id is None:
                project_id = config.get("configurable", {}).get("project_id", DEFAULT_PROJECT_ID)

            working_directory = (
                blackboard.get("working_directory") or 
                config.get("configurable", {}).get("working_directory")
            )
            thread_id = state.get("thread_id") or config.get("configurable", {}).get("thread_id")

            ctx = EvoContext(
                project_id=project_id,
                working_directory=working_directory,
                thread_id=thread_id,
                request_id=f"run-{gen_uuid()[:8]}"
            )
            ContextManager.set(ctx)
            logger.info(f"[Middleware] 🧪 Context Initialized: project_id={project_id}")

        project_id = ctx.project_id or DEFAULT_PROJECT_ID
        session_id = config.get("configurable", {}).get("run_id", ctx.request_id)
        thread_id = ctx.thread_id

        # Extract last human message for memory operations
        last_human_msg = ""
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                last_human_msg = msg.content
                break

        # 2. Memory Loading (Predictive Cache Strategy)
        # Try pre-loaded cache first (populated by bg task), fallback to direct query
        memory_data = {}
        if last_human_msg and settings.USE_NEO4J_MEMORY and not state.get("is_subtask"):
            memory_start = time.time()
            
            # Try predictive cache first
            from app.core.engine.predictive_memory_loader import get_predictive_memory, clear_predictive_memory
            
            current_run_id = config.get("configurable", {}).get("run_id")
            cached_memory = await get_predictive_memory(
                thread_id=thread_id,
                human_message=last_human_msg,
                project_id=project_id,
                run_id=current_run_id
            )
            
            if cached_memory:
                # Cache hit! Use pre-loaded data
                memory_data['project_concepts'] = cached_memory.get('concepts')
                memory_data['episodes'] = cached_memory.get('episodes')
                
                memory_elapsed = (time.time() - memory_start) * 1000
                logger.info(f"[Middleware] ✓ Memory from predictive cache in {memory_elapsed:.1f}ms")
                
                # Clear cache to prevent reuse (one-time use per request)
                await clear_predictive_memory(thread_id)
            else:
                # Cache miss - fallback to direct Neo4j query
                logger.debug(f"[Middleware] Predictive cache miss, falling back to Neo4j query")
                
                from app.core.memory import memory_manager
                
                concepts = await memory_manager.long_term.search_concepts(last_human_msg, project_id)
                if concepts:
                    memory_data['project_concepts'] = "\n".join([
                        f"- **{c.name}**: {c.description}" for c in concepts[:3]
                    ])
                
                episodes = await memory_manager.episodic.search_episodes(last_human_msg, project_id, limit=3)
                if episodes:
                    filtered = [
                        e for e in episodes
                        if getattr(e, "source_message_id", None) != current_run_id
                    ]
                    if filtered:
                        memory_data['episodes'] = "\n".join([e.summary for e in filtered[:2]])
                
                memory_elapsed = (time.time() - memory_start) * 1000
                logger.info(f"[Middleware] ✓ Memory from Neo4j in {memory_elapsed:.1f}ms")

        # 3. Static Layer (with caching)
        # These don't change during a request, safe to cache
        async def _load_static_data():
            """Load static context data (excluding memory which is handled above)."""
            data = {}
            
            # Inject pre-loaded memory data
            if memory_data:
                data.update(memory_data)
            
            # Skills index
            from app.core.learning.discovery import skill_discovery
            data['active_skills'] = await skill_discovery.get_active_skills_list()
            
            # Environment telemetry
            from app.core.environment import get_awakened_state
            env_state = get_awakened_state()
            if env_state:
                data['telemetry'] = {
                    "android": [{"id": d.device_id, "reachable": d.is_reachable} 
                               for d in env_state.android_devices],
                    "macos": bool(env_state.macos),
                    "network": env_state.network.internet_connected if env_state.network else False
                }
            
            return data
        
        # Load static layer with caching
        static_layer = await LayeredContextCache.get_static_layer(
            session_id=session_id,
            project_id=project_id,
            loader_fn=_load_static_data
        )
        
        # Apply static layer to context
        ctx.metadata["project_concepts"] = static_layer.project_concepts
        ctx.metadata["active_skills"] = static_layer.active_skills_index
        ctx.metadata["environment_telemetry"] = static_layer.environment_telemetry
        
        # 4. Dynamic Layer (always fresh, never cached)
        # These change between nodes and must be current
        dynamic_layer = LayeredContextCache.get_dynamic_layer(state)
        
        ctx.metadata["blackboard"] = dynamic_layer.blackboard
        ctx.metadata["execution_ticket"] = dynamic_layer.execution_ticket
        ctx.metadata["iteration_count"] = dynamic_layer.iteration_count
        
        # 5. Environment Hydration (always run for plugin discovery)
        from app.core.context.plugins import plugin_registry
        plugin_registry.hydrate_context(ctx)

        # 6. State Harmonization
        if not blackboard.get("verification") and state.get("verification_status"):
            blackboard["verification"] = state.get("verification_status")

        # 7. Metadata Reset (Industrial Hardening)
        is_retry = config.get("metadata", {}).get("is_retry", False)
        
        if (state.get("is_retry") or is_retry) and not state.get("is_subtask"):
            logger.info("[Middleware] 🔄 Retry detected: Performing deep blackboard cleanup.")
            for key in ["ticket", "verification", "route_reason"]:
                blackboard[key] = None
            if "metadata" in blackboard:
                for key in ["final_outcome", "shadow_audit"]:
                    if key in blackboard["metadata"]:
                        del blackboard["metadata"][key]
            # Also invalidate static cache on retry
            LayeredContextCache.invalidate_static(session_id)
            
        elif "metadata" in blackboard and not state.get("is_subtask"):
            for key in ["final_outcome", "shadow_audit"]:
                if key in blackboard["metadata"]:
                    logger.debug(f"[Middleware] Resetting terminal metadata '{key}' for new run.")
                    del blackboard["metadata"][key]

        # 8. Ticket Synchronization
        execution_ticket = state.get("execution_ticket")
        if execution_ticket and not blackboard.get("ticket"):
            blackboard["ticket"] = execution_ticket

        state["blackboard"] = blackboard
        
        # Log performance
        duration_ms = (time.time() - start_time) * 1000
        logger.debug(f"[Middleware] Hydration completed in {duration_ms:.1f}ms")
        
        return state
