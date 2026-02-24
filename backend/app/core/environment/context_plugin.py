import logging

from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.core.environment.boundaries import boundary_manager
from app.core.environment.prompt import build_environment_summaries

logger = logging.getLogger(__name__)


class EnvironmentContextPlugin(ContextPlugin):
    """
    Injects dynamic environmental state and active boundaries
    into the EvoContext (Subconscious Pool).
    """
    def hydrate(self, ctx: EvoContext) -> None:
        try:
            from app.core.environment import get_awakened_state

            # 1. Hydrate Active Boundaries
            boundaries = boundary_manager.get_all_boundaries()
            # We copy it over to avoiding attaching the reference
            ctx.active_boundaries = list(boundaries)

            # 2. Hydrate Environment Summaries
            ctx.environment_summaries = build_environment_summaries(relevance="auto")
            ctx.spatial_awareness = []

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
                        ctx.spatial_awareness.append(f"New Apps Found: {', '.join(all_new_apps[:5])}")
                    if all_missing_skills:
                        ctx.spatial_awareness.append(f"Missing Expert Guides: {', '.join(set(all_missing_skills))}")

                    verified_layouts = []
                    if getattr(state, "relevant_concepts", None):
                        for c in state.relevant_concepts:
                            if c.name.startswith("android_layout:"):
                                verified_layouts.append(c.name.split(":", 1)[1])
                    if verified_layouts:
                        ctx.spatial_awareness.append(f"Verified UI Baselines: {', '.join(verified_layouts)}")

                    macos_verified = report.get("macos", {}).get("verified_apps", [])
                    if macos_verified:
                        ctx.spatial_awareness.append(f"MacOS Tools Verified: {', '.join(macos_verified)}")

                # 4. Hydrate Memory Replay & Identity Rules
                ctx.memory_replay = []
                ctx.identity_rules = []

                if getattr(state, "recent_episodes", None):
                    ctx.memory_replay.append("**Recent Tasks:**")
                    for ep in state.recent_episodes[:3]:
                        ctx.memory_replay.append(f"- [{ep.date}] {ep.goal} → {ep.result}")

                if getattr(state, "relevant_concepts", None):
                    unique_names = []
                    # package_id -> display_name
                    layout_map = {}
                    seen_others = set()
                    
                    for c in state.relevant_concepts:
                        name = c.name
                        if name.startswith("android_layout:"):
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
                    
                    # Re-assemble layouts
                    formatted_layouts = [f"android_layout({val})" for val in layout_map.values()]
                    final_concepts = formatted_layouts + unique_names
                    
                    concept_names = ", ".join(final_concepts[:5])
                    ctx.memory_replay.append(f"**Key Knowledge:** {concept_names}")

                if getattr(state, "journal_highlights", None):
                    ctx.memory_replay.append(f"**Recent Learnings:**\n{state.journal_highlights}")

                if getattr(state, "user_preferences", None):
                    prefs = ", ".join([f"{k}={v}" for k, v in list(state.user_preferences.items())[:5]])
                    ctx.identity_rules.append(f"- **User Preferences**: {prefs}")

                if getattr(state, "system_rules", None):
                    ctx.identity_rules.append("- **Inviolable Rules**:")
                    for rule in state.system_rules[:3]:
                        ctx.identity_rules.append(f"  - ❌ {rule}")

        except Exception as e:
            logger.error(f"Failed to hydrate EnvironmentContextPlugin: {e}")


# Register the plugin instance
plugin_registry.register(EnvironmentContextPlugin())
