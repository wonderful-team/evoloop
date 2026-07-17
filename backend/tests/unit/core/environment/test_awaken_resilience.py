"""Awakening must survive individual probe failures.

Regression: a slow Spotlight (mdfind) query raised TimeoutExpired inside the
host probe, and asyncio.gather propagated it — the whole awaken() died, so no
AwakenedState, no capability boundaries, no awakening-complete event."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.environment.lifecycle import awaken
from app.core.environment.schemas.models import PreferenceContext


@pytest.mark.asyncio
async def test_awaken_survives_probe_failures():
    with (
        patch("app.core.environment.lifecycle.EnvironmentProbe") as probe,
        patch(
            "app.core.environment.lifecycle.replay_memory",
            new=AsyncMock(side_effect=TimeoutError("mdfind stuck")),
        ),
        patch(
            "app.core.environment.lifecycle.prime_preferences",
            new=AsyncMock(return_value=PreferenceContext(preferences={"theme": "dark"})),
        ),
        patch(
            "app.core.environment.event.publishers.publish_awakening_complete",
            new=AsyncMock(),
        ) as pub,
    ):
        probe.probe_host = AsyncMock(side_effect=TimeoutError("mdfind"))
        probe.probe_android_devices = AsyncMock(return_value=[])
        probe.probe_network = AsyncMock(side_effect=RuntimeError("no net"))
        probe.probe_docker_containers = AsyncMock(return_value=[])

        state = await awaken()

    assert state.host is None
    assert state.recent_episodes == []
    assert state.user_preferences == {"theme": "dark"}
    pub.assert_awaited_once()


@pytest.mark.asyncio
async def test_ranker_tolerates_mdfind_timeout():
    """TimeoutExpired (not an OSError) must not escape the usage ranker."""
    import subprocess

    from app.core.environment.usage.ranker import UsageRanker

    with (
        patch.object(UsageRanker, "_get_running_macos_apps", return_value=set()),
        patch(
            "app.core.environment.usage.ranker.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["mdfind"], timeout=10),
        ),
        patch.object(UsageRanker, "_probe_macos_path", return_value=None),
    ):
        records = UsageRanker.rank_macos_apps([], top_n=10)

    assert records == []
