import logging

from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.core.environment.boundaries import boundary_manager
from app.core.environment.prompt import (
    AppEnvironmentPrompt,
    build_environment_summaries,
)

logger = logging.getLogger(__name__)


class EnvironmentContextPlugin(ContextPlugin):
    """
    Injects dynamic environmental state and active boundaries
    into the EvoContext (Subconscious Pool).
    """

    _LOAD_FOR_INTENTS: frozenset[str | None] = frozenset({
        None, "environment_query", "worker_task", "ambiguous", "macro_task",
    })

    def is_needed(self, intent: str | None) -> bool:
        """Only pay the sensing cost when the intent may require it."""
        return intent in self._LOAD_FOR_INTENTS

    def hydrate(self, ctx: EvoContext) -> None:
        # Reset to avoid carrying stale summaries into intents that skip hydration.
        ctx.environment_summaries = {}

        try:
            from app.core.environment import get_awakened_state
            state = get_awakened_state()

            # 1. Hydrate Active Boundaries
            ctx.active_boundaries = list(boundary_manager.get_all_boundaries())

            # 2. Hydrate Environment Summaries
            ctx.environment_summaries = build_environment_summaries(relevance="auto")

            if not isinstance(ctx.spatial_awareness, dict):
                ctx.spatial_awareness = {}

            # Reset metadata flags
            ctx.metadata.has_android = False
            ctx.metadata.has_macos = False

            if state:
                if state.android_devices:
                    ctx.metadata.has_android = True
                if state.host and state.host.os_name == "macOS":
                    ctx.metadata.has_macos = True

                # 3. Hydrate Memory Replay
                ctx.memory_replay = {}

                if state.recent_episodes:
                    ctx.memory_replay["episodes"] = [
                        {"date": ep.date, "goal": ep.goal, "result": ep.result}
                        for ep in state.recent_episodes[:3]
                    ]

                if state.relevant_concepts:
                    unique_names = []
                    layout_map = {}
                    seen_others = set()

                    for c in state.relevant_concepts:
                        name = c.name
                        android_prefixes = ("android_layout:", "android:", "adb:", "mobile:", "apk:")
                        if name.lower().startswith(android_prefixes):
                            # Extract package: android_layout:com.pkg -> com.pkg
                            parts = name.split(":", 1)
                            if len(parts) > 1:
                                pkg = parts[1].strip()
                                # Clean up common app names if they are in the pkg string (heuristic)
                                # e.g. "Alibaba Cloud (com.alibaba.aliyun)"
                                if "(" in pkg and ")" in pkg:
                                    # Deep deduplication: Extract just the ID inside brackets
                                    import re
                                    match = re.search(r'\((.*?)\)', pkg)
                                    pkg_id = match.group(1) if match else pkg
                                else:
                                    pkg_id = pkg

                                # Only keep the most descriptive one (heuristic: longest string)
                                if pkg_id not in layout_map or len(pkg) > len(layout_map[pkg_id]):
                                    layout_map[pkg_id] = pkg
                        else:
                            if name not in seen_others:
                                unique_names.append(name)
                                seen_others.add(name)

                    # Always include layouts if discovered
                    formatted_layouts = [f"android_layout({val})" for val in list(layout_map.values())[:5]]

                    ctx.memory_replay["concepts"] = (formatted_layouts + unique_names[:5])[:5]

                if state.journal_highlights:
                    ctx.memory_replay["highlights"] = state.journal_highlights

                # Pass raw user preferences to templates for rendering
                if state.user_preferences:
                    ctx.metadata.user_preferences = state.user_preferences

            # Compute the final Environment Block (Autonomous Sensing Output)
            # This pre-rendered block is what the Engine will use.
            ctx.environment_block = AppEnvironmentPrompt.render_environment_block(skip_hydrate=True)

        except Exception:
            logger.exception("Failed to hydrate EnvironmentContextPlugin")


# Register the plugin instance
plugin_registry.register(EnvironmentContextPlugin())
