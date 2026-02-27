import logging

from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.core.environment.boundaries import boundary_manager
from app.core.environment.prompt import build_environment_summaries, AppEnvironmentPrompt

logger = logging.getLogger(__name__)


class EnvironmentContextPlugin(ContextPlugin):
    """
    Injects dynamic environmental state and active boundaries
    into the EvoContext (Subconscious Pool).
    """
    def hydrate(self, ctx: EvoContext) -> None:
        try:
            from app.core.environment import get_awakened_state
            state = get_awakened_state()
            has_android = False
            if state and state.android_devices:
                has_android = True

            # 1. Hydrate Active Boundaries
            boundaries = boundary_manager.get_all_boundaries()
            if not has_android:
                # Remove Android-specific boundaries if no device connected
                android_keywords = ("adb", "android", "phone", "mobile", "apk")
                ctx.active_boundaries = [b for b in boundaries if not any(k in b.lower() for k in android_keywords)]
            else:
                ctx.active_boundaries = list(boundaries)

            # 2. Hydrate Environment Summaries
            ctx.environment_summaries = build_environment_summaries(relevance="auto")
            
            if not isinstance(ctx.spatial_awareness, dict):
                ctx.spatial_awareness = {}

            # 2.5 Compute the final Environment Block (Autonomous Sensing Output)
            # This pre-rendered block is what the Engine will use.
            ctx.environment_block = AppEnvironmentPrompt.render_environment_block(skip_hydrate=True)
            
            state = get_awakened_state()
            
            # Reset metadata flags
            ctx.metadata["has_android"] = False
            ctx.metadata["has_macos"] = False

            if state:
                if state.android_devices:
                    ctx.metadata["has_android"] = True
                if state.macos:
                    ctx.metadata["has_macos"] = True

                # 3. Hydrate Spatial Awareness (Discovery Report)
                if getattr(state, "discovery_report", None):
                    report = state.discovery_report
                    all_new_apps = []
                    all_missing_skills = []

                    for device_serial, discovery in report.get("android", {}).items():
                        if discovery.get("new_apps_found"):
                            all_new_apps.extend(discovery["new_apps_found"])
                        if discovery.get("missing_skills"):
                            all_missing_skills.extend(discovery["missing_skills"])

                    if all_new_apps:
                        ctx.spatial_awareness["new_apps"] = all_new_apps[:5]
                    if all_missing_skills:
                        ctx.spatial_awareness["missing_skills"] = list(set(all_missing_skills))

                    verified_layouts = []
                    if getattr(state, "relevant_concepts", None):
                        for c in state.relevant_concepts:
                            if c.name.startswith("android_layout:"):
                                verified_layouts.append(c.name.split(":", 1)[1])
                    if verified_layouts and state.android_devices:
                        ctx.spatial_awareness["verified_layouts"] = verified_layouts

                    macos_verified = report.get("macos", {}).get("verified_apps", [])
                    if macos_verified:
                        ctx.spatial_awareness["macos_verified"] = macos_verified

                # 4. Hydrate Memory Replay
                ctx.memory_replay = {}

                if getattr(state, "recent_episodes", None):
                    ctx.memory_replay["episodes"] = [
                        {"date": ep.date, "goal": ep.goal, "result": ep.result}
                        for ep in state.recent_episodes[:3]
                    ]

                if getattr(state, "relevant_concepts", None):
                    unique_names = []
                    # package_id -> display_name
                    layout_map = {}
                    seen_others = set()
                    
                    for c in state.relevant_concepts:
                        name = c.name
                        android_prefixes = ("android_layout:", "android:", "adb:", "mobile:", "apk:")
                        if name.lower().startswith(android_prefixes):
                            if not has_android:
                                continue
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

                    # Re-assemble layouts only if android is available
                    formatted_layouts = []
                    if has_android:
                        formatted_layouts = [f"android_layout({val})" for val in layout_map.values()]

                    ctx.memory_replay["concepts"] = (formatted_layouts + unique_names)[:5]

                if getattr(state, "journal_highlights", None):
                    ctx.memory_replay["highlights"] = state.journal_highlights

                # Pass raw user preferences to templates for rendering
                if getattr(state, "user_preferences", None):
                    ctx.metadata["user_preferences"] = state.user_preferences

        except Exception as e:
            logger.error(f"Failed to hydrate EnvironmentContextPlugin: {e}")


# Register the plugin instance
plugin_registry.register(EnvironmentContextPlugin())
