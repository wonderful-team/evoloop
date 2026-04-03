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
from app.core.context.cache import LayeredContextCache
from app.core.engine.hooks import hook_system, HookEvent, HookContext
from app.infrastructure.config.service import SystemConfigService
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class EvoContextMiddleware:
    """
    Middleware for unified context and state management.
    Handles hydration of Environment, Project, and Memory before session execution.
    
    Optimization:
    - Hydration deduplication: Uses _hydrated marker to skip redundant hydration
      within the same request lifecycle, saving ~75ms per request.
    - Single Container: Creates MemoryContainer once and reuses for all memory operations
    """
    
    HYDRATION_MARKER = "_hydrated_v1"
    HYDRATION_VERSION = "2024.1"  # Bump this if hydration logic changes

    @staticmethod
    async def hydrate(state: dict, config: RunnableConfig) -> dict:
        """
        Layered context hydration with caching and predictive memory loading.
        
        Optimizations:
        - Hydration Deduplication: Skips if already hydrated in this request
        - Single MemoryContainer: Creates container once and reuses for all memory operations
        - Predictive Memory: Tries Redis cache first (populated by bg task in chat_endpoint)
        - Static layer (cacheable): Project concepts, skills, telemetry
        - Dynamic layer (always fresh): Blackboard, execution state, messages
        """
        start_time = time.time()
        memory_container = None  # Will be initialized on first memory access
        
        # Helper function to get or create memory container
        async def _get_memory_container():
            nonlocal memory_container
            if memory_container is None:
                from app.core.memory import MemoryContainer, MemoryConfig
                memory_container = MemoryContainer(MemoryConfig.from_settings())
                await memory_container.initialize()
                logger.debug("[Middleware] MemoryContainer initialized")
            return memory_container
        
        # OPTIMIZATION: Hydration Deduplication
        # Check if already hydrated in this request lifecycle
        # This saves ~75ms by avoiding redundant hydration across Supervisor/Worker/Finish nodes
        if state.get(EvoContextMiddleware.HYDRATION_MARKER) == EvoContextMiddleware.HYDRATION_VERSION:
            logger.debug(f"[Middleware] ⏭️ Skipping duplicate hydration for request")
            return state
        
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
        
        # 1b. Trigger SessionStart Hook
        # This allows hooks to initialize state, load context, etc.
        try:
            session_start_result = await hook_system.trigger(
                HookEvent.SESSION_START,
                HookContext(
                    thread_id=ctx.thread_id,
                    project_id=ctx.project_id,
                    user_id=ctx.user_id,
                    blackboard=blackboard,
                ),
            )
            if session_start_result.modified_context:
                # Update blackboard if hook modified it
                blackboard.update(session_start_result.modified_context.blackboard)
                logger.debug("[Middleware] SessionStart hook modified context")
        except Exception as e:
            logger.warning(f"[Middleware] SessionStart hook failed: {e}")

        project_id = ctx.project_id or DEFAULT_PROJECT_ID
        session_id = config.get("configurable", {}).get("run_id", ctx.request_id)
        thread_id = ctx.thread_id

        # Extract last human message for memory operations
        last_human_msg = ""
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                content = msg.content
                # Handle list content (e.g., Anthropic message format)
                if isinstance(content, list):
                    # Extract text from content blocks
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    last_human_msg = " ".join(text_parts)
                else:
                    last_human_msg = str(content) if content else ""
                break

        # 2. Memory Loading (Predictive Cache Strategy)
        # Try pre-loaded cache first (populated by bg task), fallback to direct query
        memory_data = {}
        if last_human_msg and not state.get("is_subtask"):
            memory_start = time.time()
            current_run_id = config.get("configurable", {}).get("run_id")
            
            if settings.USE_NEO4J_MEMORY:
                # Neo4j mode: Use predictive loader
                from app.core.engine.predictive_memory_loader import get_predictive_memory, clear_predictive_memory
                
                cached_memory = await get_predictive_memory(
                    thread_id=thread_id,
                    human_message=last_human_msg,
                    project_id=project_id,
                    run_id=current_run_id
                )
                
                if cached_memory:
                    memory_data['project_concepts'] = cached_memory.get('concepts')
                    memory_data['episodes'] = cached_memory.get('episodes')
                    
                    memory_elapsed = (time.time() - memory_start) * 1000
                    logger.info(f"[Middleware] ✓ Memory from predictive cache in {memory_elapsed:.1f}ms")
                    await clear_predictive_memory(thread_id)
                else:
                    # Cache miss - fallback to direct query using shared container
                    logger.debug(f"[Middleware] Predictive cache miss, falling back to Neo4j query")
                    
                    try:
                        container = await _get_memory_container()
                        memory_manager = container.memory_manager
                        concepts = await memory_manager.long_term.search_concepts(last_human_msg, project_id)
                        if concepts:
                            memory_data['project_concepts'] = "\n".join([
                                f"- **{c.name}**: {c.description}" for c in concepts[:3]
                            ])
                        
                        episodes = await memory_manager.long_term.find_episodes_by_concept(last_human_msg, project_id, limit=3)
                        if episodes:
                            filtered = [e for e in episodes if getattr(e, "source_message_id", None) != current_run_id]
                            if filtered:
                                memory_data['episodes'] = "\n".join([e.summary for e in filtered[:2]])
                        
                        memory_elapsed = (time.time() - memory_start) * 1000
                        logger.info(f"[Middleware] ✓ Memory from Neo4j in {memory_elapsed:.1f}ms")
                    except Exception as e:
                        logger.warning(f"[Middleware] Failed to load Neo4j memory: {e}")
            else:
                # Embedded mode: Use smart retrieval with LLM selection
                # OPTIMIZATION: Use shared container instead of creating new one via get_relevant_memories
                from app.core.memory.smart_retrieval import SmartMemoryRetriever
                from app.core.memory.state_tracking import memory_tracker
                
                try:
                    container = await _get_memory_container()
                    
                    # Get already-surfaced memories to avoid repetition
                    already_surfaced = memory_tracker.get_surfaced_ids(thread_id)
                    
                    # Create retriever with shared container's storage
                    retriever = SmartMemoryRetriever(
                        storage=container.storage,
                        config=container.config,
                        max_results=5,
                    )
                    
                    user_id = ctx.user_id
                    entries = await retriever.find_relevant(
                        query=last_human_msg,
                        context={
                            "user_id": user_id,
                            "project_id": project_id,
                        },
                        already_surfaced=already_surfaced,
                    )
                    
                    if entries:
                        # Format entries as project concepts
                        formatted_entries = []
                        for entry in entries:
                            emoji = {"user": "👤", "feedback": "💬", "project": "📁", "reference": "📖"}.get(entry.type.value, "📄")
                            formatted_entries.append(
                                f"{emoji} **{entry.title}** ({entry.type.value})\n"
                                f"{entry.content[:300]}"
                            )
                        memory_data['project_concepts'] = "\n\n".join(formatted_entries)
                        memory_data['embedded_memories'] = entries  # Store for later reference
                        
                        # Mark as surfaced to avoid showing again in this session
                        memory_tracker.mark_surfaced(thread_id, [e.id for e in entries])
                    
                    memory_elapsed = (time.time() - memory_start) * 1000
                    logger.info(f"[Middleware] ✓ Memory from smart retrieval: {len(entries)} entries in {memory_elapsed:.1f}ms")
                except Exception as e:
                    logger.warning(f"[Middleware] Failed to load embedded memory: {e}")
        
        # 2b. Load Tier 1 Hot Memory (Two-Tier Architecture)
        # This is always loaded from MEMORY.md - most important knowledge
        # OPTIMIZATION: Use shared container instead of creating new one
        try:
            container = await _get_memory_container()
            memory_manager = container.memory_manager
            hot_memory = await memory_manager.get_hot_memory()
            if hot_memory:
                memory_data['hot_memory'] = hot_memory
                logger.info(f"[Middleware] ✓ Hot memory loaded: {len(hot_memory.split(chr(10)))} lines")
        except Exception as e:
            logger.warning(f"[Middleware] Failed to load hot memory: {e}")

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
        
        # Mark as hydrated to prevent redundant calls
        # This marker is checked at the beginning of hydrate() to skip duplicate work
        state[EvoContextMiddleware.HYDRATION_MARKER] = EvoContextMiddleware.HYDRATION_VERSION
        
        # Cleanup: Shutdown memory container if it was created
        if memory_container is not None:
            try:
                await memory_container.shutdown()
                logger.debug("[Middleware] MemoryContainer shutdown")
            except Exception as e:
                logger.warning(f"[Middleware] Failed to shutdown MemoryContainer: {e}")
        
        # Log performance
        duration_ms = (time.time() - start_time) * 1000
        logger.debug(f"[Middleware] Hydration completed in {duration_ms:.1f}ms")
        
        return state
