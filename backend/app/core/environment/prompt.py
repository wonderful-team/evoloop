"""
App Environment Prompt

Centralizes the logic for generating the "Awakening" section of the system prompt.
This ensures both the Supervisor and Skills share the same understanding of the environment.
"""


from app.core.environment import get_awakened_state
from app.core.environment.prompt_utils import (
    build_environment_prompt,
    detect_platform_relevance,
)


class AppEnvironmentPrompt:
    """
    Generates the environment context string based on the current AwakenedState.
    """

    @staticmethod
    def build(messages: list[dict] = None) -> str:
        """
        Build the environment context string.
        
        Args:
            messages: Optional conversation history to detect context relevance 
                      (e.g. if user is talking about Android, show more Android details).
        
        Returns:
            Formatted string suitable for System Prompt injection.
        """
        try:
            state = get_awakened_state()
            if not state:
                return ""

            # Detect Relevance
            relevance = detect_platform_relevance(messages or [])

            sections = ["\n## 🌅 ENVIRONMENT AWARENESS\n"]

            # --- Environment Details ---
            sections.append(build_environment_prompt(relevance=relevance))

            # --- Memory Replay ---
            if state.recent_episodes or state.relevant_concepts or state.journal_highlights:
                sections.append("\n### 🧠 Memory Replay (What I Remember)")

                if state.recent_episodes:
                    sections.append("**Recent Tasks:**")
                    for ep in state.recent_episodes[:3]:
                        sections.append(f"- [{ep.date}] {ep.goal} → {ep.result}")

                if state.relevant_concepts:
                    concept_names = ", ".join([c.name for c in state.relevant_concepts[:5]])
                    sections.append(f"**Key Knowledge:** {concept_names}")

                if state.journal_highlights:
                    sections.append(f"**Recent Learnings:**\n{state.journal_highlights}")

            # --- Preferences & Rules ---
            if state.user_preferences or state.system_rules:
                sections.append("\n### 🎭 Identity & Rules")

                if state.user_preferences:
                    prefs = ", ".join([f"{k}={v}" for k, v in list(state.user_preferences.items())[:5]])
                    sections.append(f"- **User Preferences**: {prefs}")

                if state.system_rules:
                    sections.append("- **Inviolable Rules**:")
                    for rule in state.system_rules[:3]:
                        sections.append(f"  - ❌ {rule}")

            # --- Capability Boundaries ---
            if state.capability_boundaries:
                sections.append("\n### ❌ Constraints")
                for boundary in state.capability_boundaries[:4]:
                    sections.append(f"- {boundary}")

            # --- Pro Tip: App Atlas ---
            sections.append("\n💡 **PRO TIP**: You can use the `query_app_atlas` tool to retrieve structural UI maps (Atlas) for known applications (e.g. Navicat). Use this to find menu paths or button locations without excessive exploration.")

            return "\n".join(sections) + "\n"

        except Exception:
            return ""
