"""
EvoContextMiddleware - Unified context hydration with Predictive Memory Loading.

This module implements the Pre-Supervisor optimization strategy:
1. Predictive Memory Loading: Semantic search results are pre-loaded in background
   during LangGraph initialization, reducing ~800ms Neo4j query to ~1ms Redis read.
2. Layered Caching: Static data (skills, telemetry) cached vs Dynamic data (blackboard) fresh.
"""

import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.context import ContextManager, EvoContext
from app.core.context.cache import LayeredContextCache
from app.core.engine.hooks import HookContext, HookEvent, hook_system
from app.core.engine.message.utils import get_message_text
from app.core.engine.state import AgentState
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
    - Request-level caching: Tracks hydrated requests to avoid redundant work
    """

    HYDRATION_MARKER = "_hydrated_v1"
    HYDRATION_VERSION = "2024.1"  # Bump this if hydration logic changes

    # Request-level hydration tracking to avoid duplicate hydration across nodes
    # Key: request_id, Value: timestamp when hydrated
    _hydrated_requests: dict[str, float] = {}
    _hydration_ttl: float = 30.0  # 30 seconds TTL for request hydration tracking
    _hydration_lock: Any = None  # Lock for thread-safe access to _hydrated_requests

    # Shared MemoryContainer for efficiency
    _memory_container: Any = None
    _container_lock: Any = None

    @classmethod
    def _get_container_lock(cls):
        """Lazy initialization of async lock."""
        if cls._container_lock is None:
            import asyncio
            cls._container_lock = asyncio.Lock()
        return cls._container_lock

    @classmethod
    def _get_hydration_lock(cls):
        """Lazy initialization of thread-safe lock for hydration tracking."""
        if cls._hydration_lock is None:
            import threading
            cls._hydration_lock = threading.Lock()
        return cls._hydration_lock

    @classmethod
    async def _get_shared_memory_container(cls) -> Any:
        """Get shared MemoryContainer via MemoryLifespanManager (singleton)."""
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()

        return MemoryLifespanManager.get_container()

    @classmethod
    def _is_recently_hydrated(cls, request_id: str) -> bool:
        """Check if this request was recently hydrated."""
        with cls._get_hydration_lock():
            if request_id in cls._hydrated_requests:
                last_hydrated = cls._hydrated_requests[request_id]
                if time.time() - last_hydrated < cls._hydration_ttl:
                    return True
                # Expired, clean up
                del cls._hydrated_requests[request_id]
            return False

    @classmethod
    def _mark_hydrated(cls, request_id: str) -> None:
        """Mark a request as hydrated."""
        with cls._get_hydration_lock():
            cls._hydrated_requests[request_id] = time.time()
            # Cleanup old entries periodically
            if len(cls._hydrated_requests) > 100:
                now = time.time()
                expired = [
                    req_id for req_id, ts in cls._hydrated_requests.items()
                    if now - ts > cls._hydration_ttl
                ]
                for req_id in expired:
                    del cls._hydrated_requests[req_id]

    @staticmethod
    async def hydrate(state: AgentState, config: RunnableConfig) -> AgentState:
        """
        Layered context hydration with caching and predictive memory loading.

        Optimizations:
        - Hydration Deduplication: Skips if already hydrated in this request
        - Single MemoryContainer: Creates container once and reuses for all memory operations
        - Predictive Memory: Tries Redis cache first (populated by bg task in chat_endpoint)
        - Static layer (cacheable): Project concepts, skills, telemetry
        - Dynamic layer (always fresh): Blackboard, execution state, messages
        """
        from app.core.engine.state import ensure_state
        state = ensure_state(state)
        start_time = time.time()

        # 0. Circuit Breaker: Check for terminal errors in history or context
        # If the context has a terminal error recorded (side-channel)
        # or the last AI message was a terminal error (429, Auth, etc.), stop immediately.
        ctx = ContextManager.current()
        request_id = ctx.request_id

        terminal_source = None
        if ctx.terminal_error:
            terminal_source = f"context ({ctx.terminal_error})"
        elif state.messages:
            last_msg = state.messages[-1]
            if isinstance(last_msg, AIMessage) and getattr(last_msg, "metadata", None):
                if last_msg.metadata.get("is_terminal"):
                    terminal_source = f"history ({last_msg.metadata.get('error_type', 'unknown')})"

        if terminal_source:
            logger.warning(f"[Middleware] 🚫 Circuit Breaker: Terminal error detected in {terminal_source}. Aborting execution.")
            from app.core.exceptions import AgentTerminalException
            raise AgentTerminalException(
                message=f"Circuit Breaker triggered: {terminal_source}",
                error_type=ctx.terminal_error or "terminal_error"
            )

        # Get shared memory container (initialized once per process)
        memory_container = await EvoContextMiddleware._get_shared_memory_container()

        # OPTIMIZATION: Hydration Deduplication - Multiple layers
        # Layer 1: Check request-level tracking (for concurrent node execution)
        if request_id != "global-fallback" and EvoContextMiddleware._is_recently_hydrated(request_id):
            # Still need to update dynamic layer, but skip static hydration
            blackboard = state.blackboard
            state.blackboard = blackboard
            state.hydration_marker = EvoContextMiddleware.HYDRATION_VERSION
            return state

        # Layer 2: Check state marker (for sequential node execution)
        if state.hydration_marker == EvoContextMiddleware.HYDRATION_VERSION:
            return state

        # 1. Resolve or Create Context (ctx already fetched above for dedup check)
        blackboard = state.blackboard

        if ctx.request_id == "global-fallback" or state.is_subtask:
            project_id = state.project_id
            if project_id is None:
                project_id = config.get("configurable", {}).get("project_id", DEFAULT_PROJECT_ID)

            working_directory = (
                blackboard.working_directory
                or config.get("configurable", {}).get("working_directory")
            )
            thread_id = state.thread_id or config.get("configurable", {}).get("thread_id")
            active_model = ctx.active_model or config.get("configurable", {}).get("model")
            if not active_model:
                raise ValueError(
                    "[Middleware] No model in config or context. "
                    "Please ensure model is passed in config or EvoContext.active_model is set."
                )

            ctx = EvoContext(
                project_id=project_id,
                working_directory=working_directory,
                thread_id=thread_id,
                active_model=active_model,
                request_id=f"run-{gen_uuid()[:8]}"
            )
            ContextManager.set(ctx)
            logger.info(f"[Middleware] 🧪 Context Initialized: project_id={project_id}, model={active_model}")
        elif not ctx.thread_id:
            # Ensure thread_id is present for hooks even when ctx was pre-set externally
            fallback_thread_id = state.thread_id or config.get("configurable", {}).get("thread_id")
            if fallback_thread_id:
                ctx = ctx.model_copy(update={"thread_id": fallback_thread_id})
                ContextManager.set(ctx)
                logger.debug(f"[Middleware] Thread ID backfilled from state/config: {fallback_thread_id}")

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

        # Extract last human message for memory operations
        last_human_msg = ""
        messages = list(state.messages)
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

        # 2. Memory Loading (Unified Strategy)
        memory_data = {}
        if last_human_msg and not state.is_subtask:
            memory_start = time.time()
            current_run_id = config.get("configurable", {}).get("run_id")

            try:
                # Use unified MemoryManager from shared container
                memory_manager = memory_container.memory_manager
                
                # 1. Fetch relevant concepts
                concepts = await memory_manager.search_concepts(last_human_msg, project_id)
                if concepts:
                    memory_data['project_concepts'] = "\n".join([
                        f"- **{c.name}**: {c.description}" for c in concepts[:3]
                    ])

                # 2. Fetch relevant episodes
                episodes = await memory_manager.search_episodes(last_human_msg, project_id, limit=3)
                if episodes:
                    # Filter out current run to avoid self-reference
                    filtered = [e for e in episodes if e.get("id") != f"ep_{current_run_id}"]
                    if filtered:
                        # search_episodes returns list of dicts: {'id', 'goal', 'result', 'timestamp'}
                        memory_data['episodes'] = "\n".join([
                            f"- **Goal**: {e['goal']}\n  **Result**: {e['result']}" 
                            for e in filtered[:2]
                        ])

                memory_elapsed = (time.time() - memory_start) * 1000
                logger.info(f"[Middleware] ✓ Memory hydrated (Concepts: {len(concepts)}, Episodes: {len(episodes)}) in {memory_elapsed:.1f}ms")
                
            except Exception as e:
                logger.warning(f"[Middleware] Failed to load memory context: {e}")


        # 2b. Load Tier 1 Hot Memory (Two-Tier Architecture)
        # This is always loaded from MEMORY.md - most important knowledge
        # OPTIMIZATION: Use shared memory container already initialized above
        try:
            memory_manager = memory_container.memory_manager
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
                    "android": [{"id": d.device_id, "reachable": d.is_reachable} for d in env_state.android_devices],
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
        ctx.metadata.project_concepts = static_layer.project_concepts
        ctx.metadata.active_skills = static_layer.active_skills_index
        ctx.metadata.environment_telemetry = static_layer.environment_telemetry

        # 4. Dynamic Layer (always fresh, never cached)
        # These change between nodes and must be current
        dynamic_layer = LayeredContextCache.get_dynamic_layer(state)

        ctx.metadata.blackboard = dynamic_layer.blackboard
        ctx.metadata.execution_ticket = dynamic_layer.execution_ticket
        ctx.metadata.iteration_count = dynamic_layer.iteration_count

        # 5. Environment Hydration (always run for plugin discovery)
        from app.core.context.plugins import plugin_registry
        plugin_registry.hydrate_context(ctx)

        # 5b. Domain Expert Polishing (Event-Driven, Domain-Agnostic)
        # The Engine publishes a signal — Domain experts (Codebase, Project, etc.) subscribe
        # and autonomously polish ctx.environment_block according to their knowledge.
        # Engine has zero knowledge of specific languages, frameworks, or industry domain logic.
        try:
            from app.core.events import system_bus
            from app.core.events.base import BaseEvent
            from app.core.events.registry import SystemEventType
            polishing_event = BaseEvent(
                event_type=SystemEventType.CONTEXT_POLISHING,
                source="context_hydrator",
                data={
                    "ctx": ctx,
                    "topic": (blackboard.ticket.topic if blackboard.ticket else ""),
                }
            )
            await system_bus.publish(polishing_event)
        except Exception as e:
            logger.warning(f"[Middleware] CONTEXT_POLISHING event failed (non-fatal): {e}")

        # 6. Metadata Reset (Industrial Hardening)
        is_retry = config.get("metadata", {}).get("is_retry", False)

        if (state.is_retry or is_retry) and state.iteration_count == 0 and not state.is_subtask:
            logger.info("[Middleware] 🔄 Retry detected: Performing deep blackboard cleanup.")

            # Ensure state.is_retry is set so ContextTrimmer will apply retry cleanup
            if not state.is_retry:
                state.is_retry = True

            # Preserve ticket if it's the initial human seed (role_name="User")
            # or if it was explicitly marked as 'intended' for this run.
            current_ticket = getattr(blackboard, "ticket", None)
            if current_ticket and current_ticket.agent_config and current_ticket.agent_config.role_name == "User":
                logger.info("[Middleware] 🛡️ Preservation: Keeping initial seed ticket during retry.")
                # We wipe reason/verification but keep the ticket intent
            else:
                blackboard.ticket = None

            blackboard.verification = None
            blackboard.route_reason = None
            if blackboard.metadata is not None:
                blackboard.metadata.final_outcome = None
                blackboard.metadata.shadow_audit = None
            # Also invalidate static cache on retry
            LayeredContextCache.invalidate_static(session_id)
        else:
            if blackboard.metadata is not None:
                blackboard.metadata.final_outcome = None
                blackboard.metadata.shadow_audit = None

        state.blackboard = blackboard

        # Mark as hydrated to prevent redundant calls
        # This marker is checked at the beginning of hydrate() to skip duplicate work
        state.hydration_marker = EvoContextMiddleware.HYDRATION_VERSION

        # Track at request level for concurrent node deduplication
        if request_id != "global-fallback":
            EvoContextMiddleware._mark_hydrated(request_id)

        # Log performance (only if took significant time)
        duration_ms = (time.time() - start_time) * 1000
        if duration_ms > 50:  # Only log if hydration took > 50ms
            logger.info(f"[Middleware] Hydration completed in {duration_ms:.1f}ms")

        return state


# Backward-compatible re-exports
from app.core.engine.conversation_context import ConversationContext  # noqa: E402,F401
from app.core.engine.skill_hydrator import SkillHydrator  # noqa: E402,F401
