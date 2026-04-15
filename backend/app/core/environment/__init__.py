"""
Evoloop Awakening System - Agent Environment Awareness Module.

This module provides the Agent with a comprehensive understanding of its
operating environment, available resources, and capability boundaries.

The awakening process integrates:
1. Environment Probe - Hardware, OS, connected devices
2. Memory Replay - Recent episodes and knowledge concepts
3. Preference Priming - User preferences and system rules
"""
import asyncio
import logging
from datetime import datetime

from app.core.environment.boundaries import boundary_manager
from app.core.environment.context_plugin import EnvironmentContextPlugin
from app.core.environment.discovery import EnvironmentProbe
from app.core.environment.memory_replay import replay_memory
from app.core.environment.models import AwakenedState
from app.core.environment.preference_priming import prime_preferences
from app.core.environment.state import get_awakened_state, set_awakened_state

logger = logging.getLogger(__name__)

# Global awakened state (singleton)
# _awakened_state is now managed in .state module


async def awaken(project_id: int | None = None) -> AwakenedState:
    """
    Execute the Agent awakening process.
    
    This should be called during application startup to initialize
    the Agent's awareness of its environment and capabilities.
    
    Args:
        project_id: Optional project ID to scope memory retrieval.
        
    Returns:
        AwakenedState containing full environment context.
    """
    global _discovery_task

    logger.info("🌅 Agent awakening...")

    # 1, 2, 3. Parallel Hydration of Awareness components
    logger.info("  👁️ Awakening cognitive subsystems (Parallel)...")

    # Bundle tasks
    probe_macos_task = EnvironmentProbe.probe_macos()
    probe_android_task = EnvironmentProbe.probe_android_devices()
    probe_network_task = EnvironmentProbe.probe_network()
    memory_task = replay_memory(project_id)
    pref_task = prime_preferences(project_id)

    # Execute all
    results = await asyncio.gather(
        probe_macos_task,
        probe_android_task,
        probe_network_task,
        memory_task,
        pref_task
    )

    # Assign results
    macos, android_devices, network, memory_context, pref_context = results

    # 4. Compute capability boundaries
    boundaries = _compute_capability_boundaries(macos, android_devices, network)
    boundary_manager.set_static_boundaries(boundaries)

    # 5. Compute available platforms
    platforms = []
    if macos:
        platforms.append("macos")
    if android_devices:
        platforms.append("android")

    # 6. Assemble final state
    state = AwakenedState(
        timestamp=datetime.now(),
        macos=macos,
        android_devices=android_devices,
        network=network,
        recent_episodes=memory_context.episodes,
        relevant_concepts=memory_context.concepts,
        journal_highlights=memory_context.journal_highlights,
        user_preferences=pref_context.preferences,
        available_platforms=platforms,
        capability_boundaries=boundaries,
    )
    set_awakened_state(state)

    logger.info(f"🧠 Agent awakened. Platforms: {platforms}")

    # Publish awakening complete event
    from app.core.environment.events import AwakenEvent, EventType, event_bus
    await event_bus.publish(AwakenEvent(
        event_type=EventType.AWAKENING_COMPLETE,
        data={"platforms": platforms, "project_id": project_id}
    ))

    return state


# get_awakened_state is now imported from .state


async def _refresh_state(project_id: int | None = None) -> AwakenedState:

    logger.debug("Refreshing environment state...")

    # Probe environment (these are fast)
    macos = await EnvironmentProbe.probe_macos()
    android_devices = await EnvironmentProbe.probe_android_devices()
    network = await EnvironmentProbe.probe_network()

    # Compute boundaries
    boundaries = _compute_capability_boundaries(macos, android_devices, network)
    boundary_manager.set_static_boundaries(boundaries)

    # Compute platforms
    platforms = []
    if macos:
        platforms.append("macos")
    if android_devices:
        platforms.append("android")

    # Preserve memory/preference context from previous state
    prev_state = get_awakened_state()

    state = AwakenedState(
        timestamp=datetime.now(),
        macos=macos,
        android_devices=android_devices,
        network=network,
        recent_episodes=prev_state.recent_episodes if prev_state else [],
        relevant_concepts=prev_state.relevant_concepts if prev_state else [],
        journal_highlights=prev_state.journal_highlights if prev_state else "",
        user_preferences=prev_state.user_preferences if prev_state else {},
        available_platforms=platforms,
        capability_boundaries=boundaries,
    )
    set_awakened_state(state)
    return state


async def _refresh_network_state() -> None:
    """
    Lightweight network state refresh.
    
    Only updates network status and capability boundaries without
    re-probing devices (which are handled by DeviceWatcher).
    """
    from app.core.environment.boundaries import boundary_manager

    # Get current state
    prev_state = get_awakened_state()
    if not prev_state:
        logger.debug("No previous state, skipping network refresh")
        return

    # Only probe network (fast)
    network = await EnvironmentProbe.probe_network()

    # Recompute boundaries with new network status
    boundaries = _compute_capability_boundaries(
        prev_state.macos,
        prev_state.android_devices,
        network
    )
    boundary_manager.set_static_boundaries(boundaries)

    # Update state with new network info
    state = AwakenedState(
        timestamp=datetime.now(),
        macos=prev_state.macos,
        android_devices=prev_state.android_devices,
        network=network,
        recent_episodes=prev_state.recent_episodes,
        relevant_concepts=prev_state.relevant_concepts,
        journal_highlights=prev_state.journal_highlights,
        user_preferences=prev_state.user_preferences,
        available_platforms=prev_state.available_platforms,
        capability_boundaries=boundaries,
    )
    set_awakened_state(state)

    logger.debug(f"Network state refreshed: {'online' if network.internet_connected else 'offline'}")


def _compute_capability_boundaries(
    macos: object | None,
    android_devices: list,
    network: object,
) -> list[str]:
    """Compute what the Agent CANNOT do based on current environment.
    Uses Jinja2 template for rendering.
    """
    from app.utils import render_template

    result = render_template(
        "core/environment/capability_boundaries.prompt.j2",
        has_android_devices=bool(android_devices),
        network_connected=network.internet_connected if network else False
    )

    # Split into lines and filter empty ones
    return [line.strip() for line in result.strip().split("\n") if line.strip()]


# Re-export for convenience
__all__ = [
    "awaken",
    "get_awakened_state",
    "AwakenedState",
    "EnvironmentContextPlugin",
]
