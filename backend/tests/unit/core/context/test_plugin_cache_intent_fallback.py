"""Plugin-hydration cache consistency for telescopic context.

Regression test for the bug where repeated ``ahydrate_context(ctx)`` calls
without an explicit ``intent`` argument would land on a different cache
bucket than the initial intent-keyed hydrate call, causing
``SupervisorPromptBuilder`` / ``WorkerPromptBuilder`` / ``ContextMiddleware``
to overwrite intent-gated state (e.g. environment_summaries for
``environment_query``) with a full "none" bucket snapshot.

The fix in ``app/core.context.plugins.ContextPluginRegistry.hydrate_context``
makes the cache key fall back to ``ctx.metadata.intent_hint"]["intent"]``
when no explicit intent is supplied, so follow-up hydra calls reuse the
intent's bucket instead of running plugins again under the "none" intent.
"""

from __future__ import annotations

import pytest

from app.core.context.manager import ContextManager, EvoContext
from app.core.context.plugins import plugin_registry


class _RecordingPlugin:
    """Minimal plugin that records its call count and writes one field."""

    name = "recording"

    def __init__(self) -> None:
        self.calls = 0

    def is_needed(self, intent: str | None) -> bool:
        # Run only for "environment_query" or unknown (None) intent.
        return intent in (None, "environment_query", "worker_task")

    def hydrate(self, ctx: EvoContext) -> None:
        self.calls += 1
        ctx.environment_block = f"recording:{self.calls}"


@pytest.fixture
def _isolated_plugin_registry() -> None:
    """Snapshot the registry so the test can replace its plugin list and cache."""
    saved_plugins = list(plugin_registry._plugins)
    saved_cache = dict(plugin_registry._hydration_cache)
    plugin_registry._plugins.clear()
    plugin_registry._hydration_cache.clear()
    yield
    plugin_registry._plugins.extend(saved_plugins)
    plugin_registry._hydration_cache.clear()
    plugin_registry._hydration_cache.update(saved_cache)


@pytest.fixture
def _isolated_context() -> None:
    """Set a fresh EvoContext on the context-var so the test owns it."""
    ctx = EvoContext(thread_id="t-plugin", project_id=0)
    token = ContextManager.set(ctx)
    yield ctx
    ContextManager.reset(token)


def test_follow_up_ahydrate_reuses_intent_bucket(
    _isolated_plugin_registry: None,
    _isolated_context: EvoContext,
) -> None:
    """Builder call without intent must reuse the hydrator's intent bucket."""
    rec = _RecordingPlugin()
    plugin_registry.register(rec)
    ctx = _isolated_context

    # Simulate AgentContextHydrator.hydrate() classifying the turn as
    # environment_query and storing the dict-form IntentHint on ctx.metadata.
    ctx.metadata.intent_hint = {
        "intent": "environment_query",
        "confidence": 0.7,
        "suggested_modules": ["Base", "Environment"],
        "reason": "environment keyword",
    }
    plugin_registry.hydrate_context(ctx, intent="environment_query")
    assert rec.calls == 1
    assert ctx.environment_block == "recording:1"

    # Now simulate SupervisorPromptBuilder.build(), which calls
    # ahydrate_context(ctx) without forwarding the intent. Before the fix this
    # landed on the "none" bucket, re-ran plugins, and overwrote the state.
    plugin_registry.hydrate_context(ctx)  # no intent arg

    # The intent-bucket cache must hit and reuse the snapshot, so the plugin is
    # NOT executed again and the ctx field stays the snapshot value.
    assert rec.calls == 1, "follow-up ahydrate_context re-ran the plugin (cache miss)"
    assert ctx.environment_block == "recording:1"


def test_direct_answer_intent_not_overwritten_by_none_bucket(
    _isolated_plugin_registry: None,
    _isolated_context: EvoContext,
) -> None:
    """For direct_answer the recording plugin should be skipped and stay empty.

    Before the fix, the builder's follow-up ahydrate_context(ctx) call without
    intent went to the "none" bucket where is_needed(None) returned True and
    re-populated environment_block — undoing the direct_answer skip.
    """
    rec = _RecordingPlugin()
    plugin_registry.register(rec)
    ctx = _isolated_context

    ctx.metadata.intent_hint = {
        "intent": "direct_answer",
        "confidence": 0.9,
        "suggested_modules": ["Base"],
        "reason": "greeting",
    }
    plugin_registry.hydrate_context(ctx, intent="direct_answer")
    # direct_answer is not in the plugin's needed set → skip, no hydration.
    assert rec.calls == 0
    # environment_block wasn't written by any plugin.
    assert ctx.environment_block in (None, "", "recording:0") or ctx.environment_block is None

    # Builder follow-up call (the regression surface) — must reuse the
    # direct_answer bucket and NOT fabricate a "none" bucket run.
    plugin_registry.hydrate_context(ctx)
    assert rec.calls == 0, (
        "follow-up call without intent re-triggered the plugin under the none bucket"
    )


def test_reset_field_before_cache_apply_prevents_stale_environment(
    _isolated_plugin_registry: None,
    _isolated_context: EvoContext,
) -> None:
    """When the bucket legitimately must run, reset happens before plugin exec
    so stale environment data from a previous turn does not leak in. Ensures
    the reset+snapshot machinery still works correctly under the fix.
    """
    rec = _RecordingPlugin()
    plugin_registry.register(rec)
    ctx = _isolated_context

    # Plant stale environment_summaries as if a previous turn left them around.
    ctx.environment_summaries = {"stale": True}

    ctx.metadata.intent_hint = {
        "intent": "environment_query",
        "confidence": 0.7,
        "suggested_modules": ["Base", "Environment"],
    }
    plugin_registry.hydrate_context(ctx, intent="environment_query")
    # The plugin does not write environment_summaries directly, but
    # hydrate_context's reset must have cleared the stale value.
    assert ctx.environment_summaries != {"stale": True}