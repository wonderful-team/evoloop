"""
Evoloop Awakening System - Agent Environment Awareness Module.

This module provides the Agent with a comprehensive understanding of its
operating environment, available resources, and capability boundaries.

The awakening process integrates:
1. Environment Probe - Hardware, OS, connected devices
2. Memory Replay - Recent episodes and knowledge concepts
3. Preference Priming - User preferences and system rules
"""

import logging
from datetime import datetime
from typing import Optional

from app.core.environment.context_plugin import EnvironmentContextPlugin
from app.core.environment.discovery import EnvironmentProbe
from app.core.environment.memory_replay import replay_memory
from app.core.environment.models import AwakenedState
from app.core.environment.preference_priming import prime_preferences
from app.core.environment.watcher import environment_watcher
from app.core.environment.focus import resolve_focus, classify_ecosystems

logger = logging.getLogger(__name__)

# Global awakened state (singleton)
_awakened_state: AwakenedState | None = None


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
    global _awakened_state, _discovery_task

    logger.info("🌅 Agent awakening...")

    # 1, 2, 3. Parallel Hydration of Awareness components
    logger.info("  👁️ Awakening cognitive subsystems (Parallel)...")
    
    import asyncio
    
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

    # 5. Compute available platforms
    platforms = []
    if macos:
        platforms.append("macos")
    if android_devices:
        platforms.append("android")

    # 6. Assemble final state
    _awakened_state = AwakenedState(
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

    logger.info(f"🧠 Agent awakened. Platforms: {platforms}")

    # Publish awakening complete event
    from app.core.environment.events import AwakenEvent, EventType, event_bus
    await event_bus.publish(AwakenEvent(
        event_type=EventType.AWAKENING_COMPLETE,
        data={"platforms": platforms, "project_id": project_id}
    ))

    return _awakened_state


def get_awakened_state() -> AwakenedState | None:
    """
    Get the current awakened state.
    
    Returns None if the Agent has not been awakened yet.
    """
    return _awakened_state


async def _refresh_state(project_id: int | None = None) -> AwakenedState:
    """
    Refresh the awakened state without full re-awakening.
    
    Used by the background watcher to update state when changes are detected.
    This is lighter than a full awaken() call as it skips memory replay.
    """
    global _awakened_state

    logger.debug("Refreshing environment state...")

    # Probe environment (these are fast)
    macos = await EnvironmentProbe.probe_macos()
    android_devices = await EnvironmentProbe.probe_android_devices()
    network = await EnvironmentProbe.probe_network()

    # Compute boundaries
    boundaries = _compute_capability_boundaries(macos, android_devices, network)

    # Compute platforms
    platforms = []
    if macos:
        platforms.append("macos")
    if android_devices:
        platforms.append("android")

    # Preserve memory/preference context from previous state
    prev_state = _awakened_state

    _awakened_state = AwakenedState(
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

    logger.debug(f"Environment refreshed. Platforms: {platforms}")
    return _awakened_state


def _compute_capability_boundaries(
    macos: object | None,
    android_devices: list,
    network: object,
) -> list[str]:
    """Compute what the Agent CANNOT do based on current environment."""
    boundaries = [
        "I CANNOT perform physical actions like plugging in cables.",
    ]

    # Only mention mobile boundaries if devices are present. 
    # For common desktop tasks, don't clutter with "I can't do mobile".
    if android_devices:
        boundaries.append("Non-ASCII text input to Android via ADB may have issues.")
    
    # We keep it lean. If a user asks for iOS, the tool will fail or the Planner will handle it.
    # No need to inject denial for every single prompt.

    if not network.internet_connected:
        boundaries.append("I CANNOT access the internet (offline mode).")

    return boundaries


# Re-export for convenience
__all__ = [
    "awaken",
    "get_awakened_state",
    "AwakenedState",
    "environment_watcher",
    "EnvironmentContextPlugin",
    "resolve_focus",
    "classify_ecosystems",
]
