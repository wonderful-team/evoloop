"""
Agent Environment Lifecycle — awakening, refresh, boundary computation.

Moved from __init__.py to keep the package init clean (Batch 9 refactor).
"""

import asyncio
import logging
from datetime import datetime

from app.core.environment.boundaries import boundary_manager
from app.core.environment.discovery import EnvironmentProbe
from app.core.environment.memory_replay import replay_memory
from app.core.environment.models import AwakenedState
from app.core.environment.preference_priming import prime_preferences
from app.core.environment.state import get_awakened_state, set_awakened_state

logger = logging.getLogger(__name__)

_discovery_task: asyncio.Task | None = None


async def awaken(project_id: int | None = None) -> AwakenedState:
    global _discovery_task

    logger.info("🌅 Agent awakening...")
    logger.info("  👁️ Awakening cognitive subsystems (Parallel)...")

    probe_host_task = EnvironmentProbe.probe_host()
    probe_android_task = EnvironmentProbe.probe_android_devices()
    probe_network_task = EnvironmentProbe.probe_network()
    probe_docker_task = EnvironmentProbe.probe_docker_containers()
    memory_task = replay_memory(project_id)
    pref_task = prime_preferences(project_id)

    results = await asyncio.gather(
        probe_host_task,
        probe_android_task,
        probe_network_task,
        probe_docker_task,
        memory_task,
        pref_task,
        return_exceptions=True,
    )

    # No single subsystem failure may abort awakening (e.g. a slow Spotlight
    # query killing the host probe). Degraded probes fall back to defaults.
    from app.core.environment.schemas.models import (
        MemoryContext,
        NetworkStatus,
        PreferenceContext,
    )

    defaults = [None, [], NetworkStatus(), [], MemoryContext(), PreferenceContext()]
    names = ["host", "android", "network", "docker", "memory", "preferences"]
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.warning(f"🌅 Awakening: {names[i]} probe failed (degraded): {result}")
            results[i] = defaults[i]

    host, android_devices, network, docker_containers, memory_context, pref_context = results

    boundaries = _compute_capability_boundaries(host, android_devices, network)
    boundary_manager.set_static_boundaries(boundaries)

    platforms = []
    if host:
        platforms.append(host.os_name.lower())
    if android_devices:
        platforms.append("android")

    state = AwakenedState(
        timestamp=datetime.now(),
        host=host,
        android_devices=android_devices,
        network=network,
        docker_containers=docker_containers,
        recent_episodes=memory_context.episodes,
        relevant_concepts=memory_context.concepts,
        journal_highlights=memory_context.journal_highlights,
        user_preferences=pref_context.preferences,
        available_platforms=platforms,
        capability_boundaries=boundaries,
    )
    set_awakened_state(state)

    logger.info(f"🧠 Agent awakened. Platforms: {platforms}")

    from app.core.environment.event.publishers import publish_awakening_complete

    await publish_awakening_complete(platforms=platforms, project_id=project_id)

    return state


async def _refresh_state(project_id: int | None = None) -> AwakenedState:
    logger.debug("Refreshing environment state...")

    results = await asyncio.gather(
        EnvironmentProbe.probe_host(),
        EnvironmentProbe.probe_android_devices(),
        EnvironmentProbe.probe_network(),
        EnvironmentProbe.probe_docker_containers(),
        return_exceptions=True,
    )

    from app.core.environment.schemas.models import NetworkStatus

    defaults = [None, [], NetworkStatus(), []]
    names = ["host", "android", "network", "docker"]
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.warning(f"[Environment] Refresh: {names[i]} probe failed (degraded): {result}")
            results[i] = defaults[i]

    host, android_devices, network, docker_containers = results

    boundaries = _compute_capability_boundaries(host, android_devices, network)
    boundary_manager.set_static_boundaries(boundaries)

    platforms = []
    if host:
        platforms.append(host.os_name.lower())
    if android_devices:
        platforms.append("android")

    prev_state = get_awakened_state()

    state = AwakenedState(
        timestamp=datetime.now(),
        host=host,
        android_devices=android_devices,
        network=network,
        docker_containers=docker_containers,
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
    from app.core.environment.boundaries import boundary_manager

    prev_state = get_awakened_state()
    if not prev_state:
        logger.debug("No previous state, skipping network refresh")
        return

    network = await EnvironmentProbe.probe_network()

    boundaries = _compute_capability_boundaries(
        prev_state.host,
        prev_state.android_devices,
        network,
    )
    boundary_manager.set_static_boundaries(boundaries)

    state = AwakenedState(
        timestamp=datetime.now(),
        host=prev_state.host,
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
    host: object | None,
    android_devices: list,
    network: object,
) -> list[str]:
    from app.utils.template import render_template

    result = render_template(
        "core/environment/capability_boundaries.prompt.j2",
        has_android_devices=bool(android_devices),
        network_connected=network.internet_connected if network else False,
    )

    return [line.strip() for line in result.strip().split("\n") if line.strip()]
