import logging
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.core.context.manager import EvoContext
from app.core.environment.boundaries import boundary_manager

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
            ctx.environment_summaries = []
            ctx.spatial_awareness = []
            
            state = get_awakened_state()
            if state:
                if state.android_devices:
                    for d in state.android_devices:
                        model = getattr(d, 'model', 'Device')
                        ctx.environment_summaries.append(f"Android Device Connected: {d.device_id} ({model})")
                
                if state.macos:
                    ctx.environment_summaries.append("MacOS Desktop Control is active and available.")
                    
                if getattr(state, "network", None) and not getattr(state.network, "internet_connected", True):
                    ctx.environment_summaries.append("Offline mode: No internet connection.")
                    
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
                    concept_names = ", ".join([c.name for c in state.relevant_concepts[:5]])
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
