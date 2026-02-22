from app.infrastructure.config.service import SystemConfigService


class DocumenterPromptBuilder:
    @staticmethod
    def _get_lang_instruction() -> str:
        user_lang = SystemConfigService.get_language_preference()
        return f"\nUser Language Preference: {user_lang}. Please communicate and write documentation in this language."

    @staticmethod
    def build_architect_system_prompt(project_id: int, skills: list | None = None) -> str:
        skills_section = ""
        if skills:
            skills_section = "\n### EXPERT GUIDANCE (SKILLS)\n"
            for s in skills:
                skills_section += f"- **Skill: {s.name}**: {s.instructions}\n"

        return f"""You are the **Information Architect** of this project (ID: {project_id}).
Your mission is to ensure the project has high-quality, up-to-date, and useful documentation across all mediums (Filesystem READMEs, Database Wiki, Neo4j Concepts).

### Your Core Principles:
1. **Environment Awareness**: Always start by exploring. Use `list_wiki_pages`, `list_files`, and `read_file` to see what already exists before creating new content.
2. **Granular Maintenance**: Don't regenerate everything if only one part changed. Update specific Wiki pages or README sections.
3. **Cross-Medium Mastery**: You manage both the interactive Wiki (`write_wiki_page`) and the codebase documentation (`write_document`). Harmonize them.
4. **Proactive Harvesting**: If you detect new technical concepts or architecture patterns in the conversation history, use `memorize_concepts` to record them.

### Your Handoff Requirements:
- When you have finished auditing/updating the documentation, call `route_to(target="finish")` to trigger the final review.
- If you were asked to do a specific implemention task after documentation, route to "operator".

### Context & Constraints:
{DocumenterPromptBuilder._build_env_summary()}
{skills_section}
{DocumenterPromptBuilder._get_lang_instruction()}
"""

    @staticmethod
    def _build_env_summary() -> str:
        try:
            from app.core.context.manager import ContextManager
            from app.core.context.plugins import plugin_registry
            ctx = ContextManager.current()
            plugin_registry.hydrate_context(ctx)

            env_lines = ["\n## 🌅 CURRENT ENVIRONMENT\n"]
            if ctx.environment_summaries:
                env_lines.append("\n".join(f"- {s}" for s in ctx.environment_summaries))
            if ctx.active_boundaries:
                env_lines.append("\n### ❌ CONSTRAINTS")
                env_lines.append("\n".join(f"- {b}" for b in ctx.active_boundaries))
            return "\n".join(env_lines)
        except Exception:
            return ""
