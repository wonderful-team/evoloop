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

import psutil
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.context import ContextManager, EvoContext
from app.core.context.cache import LayeredContextCache
from app.core.engine.hooks import HookContext, HookEvent, hook_system
from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


class AgentContextHydrator:
    """
    Unified context hydration service.
    Handles hydration of Environment, Project, and Memory ONCE per session.
    """

    @classmethod
    async def _get_shared_memory_container(cls) -> Any:
        """Get shared MemoryContainer via MemoryLifespanManager (singleton)."""
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()

        return MemoryLifespanManager.get_container()

    @staticmethod
    async def hydrate(
        ctx: EvoContext,
        blackboard: Any,
        config: RunnableConfig,
        last_human_msg: str = "",
        is_retry: bool = False,
        is_subtask: bool = False,
        iteration_count: int = 0
    ) -> None:
        """
        Layered context hydration with caching and predictive memory loading.
        Mutates ctx.metadata and blackboard directly.
        """
        start_time = time.time()

        # 1. Trigger SessionStart Hook
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

        memory_data = {}
        memory_container = await AgentContextHydrator._get_shared_memory_container()
        memory_manager = memory_container.memory_manager
        
        # Tier 1: Hot Memory (High Priority Instructions)
        hot_memory = await memory_manager.get_hot_memory()
        if hot_memory:
            memory_data['hot_memory'] = hot_memory

        # Tier 2: Predictive load (Concepts & Episodes - Only for primary turns)
        if last_human_msg and not is_subtask:
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

        # 5. Static Layer (Skills, Telemetry)
        async def _load_static_data():
            data = dict(memory_data)
            from app.core.learning.discovery import skill_discovery
            data['active_skills'] = await skill_discovery.get_active_skills_list()

            from app.core.environment import get_awakened_state
            env_state = get_awakened_state()
            if env_state:
                try:
                    cpu_percent = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory()
                    active_win = None
                    if env_state.host and env_state.host.os_name == "macOS":
                        try:
                            from app.infrastructure.drivers.macos import macos_driver
                            active_win = macos_driver.get_active_window()
                        except Exception:
                            pass

                    telemetry_data = {
                        "cpu": {"usage_percent": cpu_percent, "load_avg": psutil.getloadavg() if hasattr(psutil, "getloadavg") else []},
                        "memory": {"percent": mem.percent, "available": mem.available},
                        "android": [{"id": d.device_id, "reachable": d.is_reachable} for d in env_state.android_devices],
                        "host": bool(env_state.host),
                        "active_window": active_win,
                        "network": env_state.network.internet_connected if env_state.network else False
                    }
                except Exception:
                    telemetry_data = {}
                data['telemetry'] = telemetry_data
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

        # Memory pipeline — forward cached memory data into context metadata
        # These map to Jinja2 vars: memory.core_raw / memory.episodic_raw
        ctx.metadata.core_memory_raw = static_layer.hot_memory
        ctx.metadata.episodic_memory_raw = static_layer.episodes

        # 6. Dynamic Layer & Plugins
        # We manually inject the dynamic values since we aren't using the full AgentState here
        ctx.metadata.blackboard = blackboard
        ctx.metadata.execution_ticket = blackboard.ticket if hasattr(blackboard, "ticket") else None
        ctx.metadata.iteration_count = iteration_count

        from app.core.context.plugins import plugin_registry
        plugin_registry.hydrate_context(ctx)

        # 7. Domain Expert Polishing (Event-Driven)
        from app.core.events.publishers import publish_context_polishing
        topic = ""
        if hasattr(blackboard, "ticket") and blackboard.ticket:
            topic = blackboard.ticket.topic
        await publish_context_polishing(
            thread_id=ctx.thread_id,
            project_id=ctx.project_id,
            model=ctx.active_model,
            context={
                "ctx": ctx,
                "topic": topic,
            },
        )

        # 8. Retry Hardening (Metadata Reset)
        is_config_retry = config.get("metadata", {}).get("is_retry", False)
        if (is_retry or is_config_retry) and iteration_count == 0 and not is_subtask:
            logger.info("[AgentContextHydrator] 🔄 Retry detected: Performing blackboard metadata reset.")

            if hasattr(blackboard, "metadata"):
                blackboard.metadata.final_outcome = None
                blackboard.metadata.shadow_audit = None
            if hasattr(blackboard, "verification"):
                blackboard.verification = None
            if hasattr(blackboard, "route_reason"):
                blackboard.route_reason = None
            
            # Invalidate static cache for this session to ensure fresh environment scan on retry
            LayeredContextCache.invalidate_static(session_id)
        else:
            if hasattr(blackboard, "metadata"):
                blackboard.metadata.final_outcome = None
                blackboard.metadata.shadow_audit = None

        duration_ms = (time.time() - start_time) * 1000
        if duration_ms > 100:
            logger.info(f"[AgentContextHydrator] Hydration completed in {duration_ms:.1f}ms")
