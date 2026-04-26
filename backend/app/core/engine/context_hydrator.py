"""
EvoContextMiddleware - Unified context hydration with Predictive Memory Loading.

This module implements the context hydration strategy:
1. Predictive Memory Loading: Semantic search results are loaded from Neo4j/Redis.
2. Layered Caching: Static data (skills, telemetry) cached vs Dynamic data (blackboard) fresh.
3. Industrial Hardening: Domain expert polishing, Hot Memory, and Retry logic.
"""

import logging
import time
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.context import ContextManager, EvoContext
from app.core.context.cache import LayeredContextCache
from app.core.engine.hooks import HookContext, HookEvent, hook_system
from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


class EvoContextMiddleware:
    """
    Middleware for unified context and state management.
    Handles hydration of Environment, Project, and Memory before session execution.
    
    Optimization:
    - Layered Caching: Tracks hydrated state via state.hydration_marker.
    - Single Container: Reused MemoryContainer for all operations.
    """

    HYDRATION_VERSION = "2024.1"

    @classmethod
    async def _get_shared_memory_container(cls) -> Any:
        """Get shared MemoryContainer via MemoryLifespanManager (singleton)."""
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()

        return MemoryLifespanManager.get_container()

    @staticmethod
    async def hydrate(state: AgentState, config: RunnableConfig) -> AgentState:
        """
        Layered context hydration with caching and predictive memory loading.
        """
        from app.core.engine.state import ensure_state
        state = ensure_state(state)
        
        # 0. Check hydration marker (Deduplication)
        if state.hydration_marker == EvoContextMiddleware.HYDRATION_VERSION:
            return state

        start_time = time.time()
        ctx = ContextManager.current()

        # 1. Circuit Breaker: Terminal errors
        terminal_source = None
        if ctx.terminal_error:
            terminal_source = f"context ({ctx.terminal_error})"
        elif state.messages:
            last_msg = state.messages[-1]
            if isinstance(last_msg, AIMessage) and getattr(last_msg, "metadata", None):
                if last_msg.metadata.get("is_terminal"):
                    terminal_source = f"history ({last_msg.metadata.get('error_type', 'unknown')})"

        if terminal_source:
            logger.warning(f"[Middleware] 🚫 Circuit Breaker: {terminal_source}. Aborting.")
            from app.core.exceptions import AgentTerminalException
            raise AgentTerminalException(
                message=f"Circuit Breaker triggered: {terminal_source}",
                error_type=ctx.terminal_error or "terminal_error"
            )

        # 2. Ensure Context exists (strict SSOT)
        if not ctx or not ctx.thread_id:
            logger.warning("[Middleware] No active context found during hydration. Creating minimal subtask context.")
            # Fallback for subtasks or tests that bypass dispatch
            current_thread_id = state.thread_id or config.get("configurable", {}).get("thread_id", "local-exec")
            current_model = config.get("configurable", {}).get("model")

            ctx = EvoContext(
                thread_id=current_thread_id,
                project_id=state.project_id or config.get("configurable", {}).get("project_id", DEFAULT_PROJECT_ID),
                active_model=current_model,
            )
            ContextManager.set(ctx)

        blackboard = state.blackboard

        # 3. Trigger SessionStart Hook
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
                blackboard.update(session_start_result.modified_context.blackboard)
        except Exception as e:
            logger.warning(f"[Middleware] SessionStart hook failed: {e}")

        # 4. Memory Preparation
        memory_container = await EvoContextMiddleware._get_shared_memory_container()
        memory_data = {}

        # Extract last human message
        last_human_msg = ""
        for msg in reversed(state.messages):
            if hasattr(msg, "type") and msg.type == "human":
                if isinstance(msg.content, list):
                    last_human_msg = " ".join([b.get("text", "") for b in msg.content if isinstance(b, dict) and b.get("type") == "text"])
                else:
                    last_human_msg = str(msg.content)
                break

        try:
            memory_manager = memory_container.memory_manager
            
            # Tier 1: Hot Memory (High Priority Instructions)
            hot_memory = await memory_manager.get_hot_memory()
            if hot_memory:
                memory_data['hot_memory'] = hot_memory

            # Tier 2: Predictive load (Concepts & Episodes - Only for primary turns)
            if last_human_msg and not state.is_subtask:
                concepts, episodes = await __import__("asyncio").gather(
                    memory_manager.search_concepts(last_human_msg, ctx.project_id),
                    memory_manager.search_episodes(last_human_msg, ctx.project_id, limit=3)
                )
                
                if concepts:
                    memory_data['project_concepts'] = "\n".join([f"- **{c.name}**: {c.description}" for c in concepts[:3]])
                if episodes:
                    current_run_id = config.get("configurable", {}).get("run_id")
                    filtered = [e for e in episodes if e.get("id") != f"ep_{current_run_id}"]
                    if filtered:
                        memory_data['episodes'] = "\n".join([f"- **Goal**: {e['goal']}\n  **Result**: {e['result']}" for e in filtered[:2]])
        except Exception as e:
            logger.warning(f"[Middleware] Memory hydration failed: {e}")

        # 5. Static Layer (Skills, Telemetry)
        async def _load_static_data():
            data = dict(memory_data)
            from app.core.learning.discovery import skill_discovery
            data['active_skills'] = await skill_discovery.get_active_skills_list()

            from app.core.environment import get_awakened_state
            env_state = get_awakened_state()
            if env_state:
                data['telemetry'] = {
                    "android": [{"id": d.device_id, "reachable": d.is_reachable} for d in env_state.android_devices],
                    "macos": bool(env_state.macos),
                    "network": env_state.network.internet_connected if env_state.network else False
                }
            return data

        session_id = config.get("configurable", {}).get("run_id", ctx.request_id)
        static_layer = await LayeredContextCache.get_static_layer(
            session_id=session_id,
            project_id=ctx.project_id,
            loader_fn=_load_static_data
        )

        ctx.metadata.project_concepts = static_layer.project_concepts
        ctx.metadata.active_skills = static_layer.active_skills_index
        ctx.metadata.environment_telemetry = static_layer.environment_telemetry

        # 6. Dynamic Layer & Plugins
        dynamic_layer = LayeredContextCache.get_dynamic_layer(state)
        ctx.metadata.blackboard = dynamic_layer.blackboard
        ctx.metadata.execution_ticket = dynamic_layer.execution_ticket
        ctx.metadata.iteration_count = dynamic_layer.iteration_count

        from app.core.context.plugins import plugin_registry
        plugin_registry.hydrate_context(ctx)

        # 7. Domain Expert Polishing (Event-Driven)
        try:
            from app.core.events.publishers import publish_context_polishing
            await publish_context_polishing(
                thread_id=ctx.thread_id,
                project_id=ctx.project_id,
                model=ctx.active_model,
                context={
                    "ctx": ctx,
                    "topic": (blackboard.ticket.topic if blackboard.ticket else ""),
                },
            )
        except Exception as e:
            logger.warning(f"[Middleware] CONTEXT_POLISHING event failed: {e}")

        # 8. Retry Hardening (Metadata Reset)
        is_retry = config.get("metadata", {}).get("is_retry", False)
        if (state.is_retry or is_retry) and state.iteration_count == 0 and not state.is_subtask:
            logger.info("[Middleware] 🔄 Retry detected: Performing blackboard metadata reset.")
            if not state.is_retry:
                state.is_retry = True

            # Reset stale outcomes but preserve the core intent
            if blackboard.metadata:
                blackboard.metadata.final_outcome = None
                blackboard.metadata.shadow_audit = None
            blackboard.verification = None
            blackboard.route_reason = None
            
            # Invalidate static cache for this session to ensure fresh environment scan on retry
            LayeredContextCache.invalidate_static(session_id)
        else:
            if blackboard.metadata:
                blackboard.metadata.final_outcome = None
                blackboard.metadata.shadow_audit = None

        # 9. Final State Update
        state.blackboard = blackboard
        state.hydration_marker = EvoContextMiddleware.HYDRATION_VERSION

        duration_ms = (time.time() - start_time) * 1000
        if duration_ms > 100:
            logger.info(f"[Middleware] Hydration completed in {duration_ms:.1f}ms")

        return state
