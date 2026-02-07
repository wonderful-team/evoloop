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
from typing import Optional

from app.domain.environment.models import AwakenedState
from app.domain.environment.discovery import EnvironmentProbe
from app.domain.environment.memory_replay import replay_memory
from app.domain.environment.preference_priming import prime_preferences
from app.domain.environment.active_explorer import ActiveExplorer
from app.domain.environment.watcher import environment_watcher

logger = logging.getLogger(__name__)

# Global awakened state (singleton)
_awakened_state: AwakenedState | None = None

# Background discovery task reference
_discovery_task: asyncio.Task | None = None


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
    
    # 1. Probe Environment (Fast path)
    logger.info("  👁️ Probing environment...")
    macos = EnvironmentProbe.probe_macos()
    android_devices = EnvironmentProbe.probe_android_devices()
    network = EnvironmentProbe.probe_network()
    
    # 1b. Schedule Active Discovery in background (non-blocking)
    # This allows the awakening to complete faster without waiting for device probing
    logger.info("  🔍 Scheduling active discovery (background)...")
    _discovery_task = asyncio.create_task(
        _run_active_discovery(macos, android_devices)
    )
    discovery_report = {}  # Will be populated asynchronously
    
    # 2. Replay Memory
    logger.info("  🧠 Replaying memory...")
    memory_context = await replay_memory(project_id)
    
    # 3. Prime Preferences
    logger.info("  🎭 Priming preferences...")
    pref_context = await prime_preferences(project_id)
    
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
        system_rules=pref_context.rules,
        available_platforms=platforms,
        capability_boundaries=boundaries,
        discovery_report=discovery_report,
    )
    
    logger.info(f"🧠 Agent awakened. Platforms: {platforms}")
    
    # Publish awakening complete event
    from app.domain.environment.events import event_bus, AwakenEvent, EventType
    await event_bus.publish(AwakenEvent(
        event_type=EventType.AWAKENING_COMPLETE,
        data={"platforms": platforms, "project_id": project_id}
    ))
    
    return _awakened_state


async def _run_active_discovery(macos, android_devices) -> None:
    """
    Background task for active discovery.
    
    Runs device probing and app discovery asynchronously after main awakening completes.
    Updates the global _awakened_state with discovery results when complete.
    """
    global _awakened_state
    try:
        report = await ActiveExplorer.scout(macos, android_devices)
        if _awakened_state:
            _awakened_state.discovery_report = report
            logger.info("🔍 Active Discovery complete (background)")
    except Exception as e:
        logger.warning(f"Active Discovery failed: {e}")


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
    macos = EnvironmentProbe.probe_macos()
    android_devices = EnvironmentProbe.probe_android_devices()
    network = EnvironmentProbe.probe_network()
    
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
        system_rules=prev_state.system_rules if prev_state else [],
        available_platforms=platforms,
        capability_boundaries=boundaries,
    )
    
    logger.debug(f"Environment refreshed. Platforms: {platforms}")
    return _awakened_state


def _compute_capability_boundaries(
    macos: Optional[object],
    android_devices: list,
    network: object,
) -> list[str]:
    """Compute what the Agent CANNOT do based on current environment."""
    boundaries = [
        "I CANNOT control iOS devices (no jailbroken hooks available).",
        "I CANNOT perform physical actions like plugging in cables.",
    ]
    
    if not android_devices:
        boundaries.append("I CANNOT control Android devices (none connected via ADB).")
    else:
        boundaries.append("Non-ASCII text input to Android via ADB may have issues.")
    
    if not network.internet_connected:
        boundaries.append("I CANNOT access the internet (offline mode).")
    
    return boundaries


# Re-export for convenience
__all__ = [
    "awaken",
    "get_awakened_state",
    "AwakenedState",
    "environment_watcher",
]
