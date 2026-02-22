import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.tools.manager import tool_manager
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class OperatorPromptBuilder:
    def __init__(self, state: AgentState, context: dict, project_id: int, skills: list[Any] | None = None):
        self.state = state
        self.context = context
        self.project_id = project_id
        self.skills = skills or []

    def build(self, config: RunnableConfig) -> str:
        """
        Builds the system prompt for the Operator Agent.
        """
        user_lang = SystemConfigService.get_value("LANGUAGE", "en")
        tree = self.context.get("project_structure", "")

        execution_ticket = self.state.get("execution_ticket", {}) or {}
        ticket_type = execution_ticket.get("ticket_type", "task").lower()

        # Phase 6: Conditional Context Injection
        non_fs_tasks = ["web_research", "wiki_update", "dynamic_task", "knowledge_harvesting", "data_analysis"]
        if ticket_type in non_fs_tasks:
            tree_section = "- Project Structure: [Omitted for Non-Filesystem Task]"
        else:
            tree_section = f"- Project Structure:\n{tree}"

        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        env_lines = []
        if ctx.environment_summaries:
            env_lines.append("\n".join(f"- {s}" for s in ctx.environment_summaries))
        else:
            env_lines.append("- Unknown environment state")

        if ctx.active_boundaries:
            env_lines.append("\n### ❌ Constraints")
            env_lines.append("\n".join(f"- {b}" for b in ctx.active_boundaries))

        if ctx.spatial_awareness:
            env_lines.append("\n### 🔍 Discovery Insights")
            env_lines.append("\n".join(f"- {s}" for s in ctx.spatial_awareness))

        env_section = "\n".join(env_lines)

        # Skills as Knowledge injection
        skills_section = self._build_skills_section()

        # Workspace Clipboard (Short-term memory)
        clipboard_section = self._build_clipboard_section()

        # MCP Inventory
        mcp_section_text = tool_manager.get_mcp_inventory()

        base_prompt = f"""You are an expert **Universal Systems Operator**.
Your goal is to complete the assigned task by executing the correct specialized tools (e.g., coding, shell, web automation, mobile, desktop).

### 1. CAPABILITIES
- **Code**: You can read/write files. Always read specific files before editing.
- **Verification**: You can run shell commands to verify changes or observe environment states.
- **Structure**: You have access to the file tree.
- **Desktop Control**: You can interact with the MacOS desktop (screenshot, click, type).
- **Mobile Control**: You can interact with connected Android devices via ADB.
- **Verification**: You MUST use `verify_ui_state` to confirm UI elements or text appeared after a click/type action.

### 2. EXECUTION PROTOCOL (The Inner Loop)
You are responsible for the ENTIRE lifecycle of this task. Do not ask for permission to use your tools.
1. **Analyze**: Understand the request, constraints, and environment.
2. **Execute**: Take the necessary actions using your tools.
3. **Verify**: IMMEDIATELY use verification tools (`verify_ui_state`, `analyze_image`, or shell checks) to ensure your actions succeeded.
    - If it fails -> Fix it (e.g., try another click, wait longer, or use recovery SOP) -> Verify again.
    - If it passes -> You are done.

### 3. ENVIRONMENT
- Language: {user_lang}
{env_section}
{tree_section}

### 4. CRITICAL RULES
- **Knowledge Retrieval**: If you are asked to perform a complex multi-step action (especially UI/Browser/Mobile automation) that is NOT in your current Expert Guidance, you MUST use the `search_skills` tool to find a Standard Operating Procedure (SOP) before attempting to guess the shell/UI commands yourself.
- **No Hallucination**: Do not reference files that are not in the tree (unless searching the web).
- **Verification**: NEVER finish a technical/operational task without verifying your work (e.g., running tests, viewing UI, reading logs). For theoretical questions or online research, this is not required.
- **Atomic Edits**: When editing local files, use `replace_file_content` for small changes or `write_to_file` for new files.
- **Device Awareness**: When using `mobile_control`, always specify the correct `device_id` from the connected devices list above.

{skills_section}
{mcp_section_text}
{clipboard_section}
"""
        return base_prompt

    def _build_clipboard_section(self) -> str:
        """
        Injects the Workspace Clipboard (Short-term memory) into the prompt.
        """
        scratchpad = self.state.get("scratchpad", {})
        clipboard = scratchpad.get("workspace_clipboard", [])

        if not clipboard:
            return ""

        blocks = [
            "### 6. WORKSPACE CLIPBOARD (Short-term memory)",
            "The following items have been stashed for your current session.",
            "**Use these to transfer data between steps or applications.**\n"
        ]

        for idx, item in enumerate(clipboard):
            content = item.get("content", "")
            mime_type = item.get("mime_type", "text/plain")
            metadata = item.get("metadata", {})

            block = f"#### Item {idx + 1} ({mime_type})\n"
            if metadata:
                meta_str = ", ".join([f"{k}: {v}" for k, v in metadata.items()])
                block += f"*Metadata*: {meta_str}\n"

            block += f"```\n{content}\n```\n"
            blocks.append(block)

        return "\n".join(blocks)

    def _build_skills_section(self) -> str:
        """
        Track 8.1: Eager Namespace Indexing
        Injects a lightweight Table of Contents for available skills in the namespace.
        The agent is instructed to use `search_skills` to read the full SOP.
        """
        if not self.skills:
            return ""

        blocks = [
            "### 5. AVAILABLE PROCEDURES DIRECTORY 📚",
            "The following Standard Operating Procedures (SOPs) are available in your current environment.",
            "⚠️ **CRITICAL: If your task matches one of these items, you MUST use the `search_skills` tool to read its full instructions before taking any action.**\n"
        ]

        for skill in self.skills:
            # Handle both lazy index dicts (Track 8.1) and eager LearnedSkill objects (legacy/fallback)
            if isinstance(skill, dict):
                skill_name = skill.get("name", "Unknown")
                skill_desc = skill.get("description", "")
            else:
                skill_name = getattr(skill, "name", "Unknown")
                skill_desc = getattr(skill, "description", "")

            block = f"- **{skill_name}**: {skill_desc}"
            blocks.append(block)

        return "\n".join(blocks)
