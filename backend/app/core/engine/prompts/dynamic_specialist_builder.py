from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentConfig, ExecutionTicket
from app.models.learning import LearnedSkill


class DynamicSpecialistPromptBuilder:
    """
    Constructs the system prompt for dynamic, ephemeral sub-agents.
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        ticket: ExecutionTicket,
        skills: list[LearnedSkill] = None,
        known_packages: dict[str, str] = None,
        known_macos_apps: dict[str, str] = None,
        clipboard: list[dict[str, Any]] = None
    ):
        self.agent_config = agent_config
        self.ticket = ticket
        self.skills = skills or []
        self.known_packages = known_packages or {}
        self.known_macos_apps = known_macos_apps or {}
        self.clipboard = clipboard or []

    def build(self, config: RunnableConfig | None = None) -> str:
        """Constructs the full system prompt."""
        role_name = self.agent_config.get("role_name", "Specialist")
        instructions = self.agent_config.get("system_instructions", "You are a helpful assistant.")

        from app.core.context.manager import ContextManager
        from app.core.context.plugins import plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        topic = self.ticket.get("topic", "").lower() + " " + instructions.lower()

        env_lines = []
        if ctx.environment_summaries:
            for s in ctx.environment_summaries:
                env_lines.append(f"- {s}")
        else:
            env_lines.append("- Unknown environment state")

        if ctx.active_boundaries:
            env_lines.append("\n### ❌ Constraints")
            for b in ctx.active_boundaries:
                env_lines.append(f"- {b}")

        env_section = "\n".join(env_lines)

        spatial_awareness_section = "Environment state matches known knowledge base."
        if ctx.spatial_awareness:
            spatial_awareness_section = "\n".join(f"- {s}" for s in ctx.spatial_awareness)

        # Sandbox Warning
        sandbox_footer = self._build_sandbox_footer()

        return f"""## Your Role: {role_name}
{instructions}

## AppleScript Protocol (CRITICAL)
If you use `desktop_control(action="applescript", script=...)`, you MUST follow these escaping rules:
- **Nested Quotes**: AppleScript strings are enclosed in double quotes `"`. If you need a double quote INSIDE a string, you MUST escape it with a backslash: `\"`. 
  - ❌ Incorrect: `keystroke "User "Name""`
  - ✅ Correct: `keystroke "User \"Name\""`
- **Shell Commands**: If using `do shell script`, remember you are nesting quotes again. Use single quotes for shell segments if possible.

## Environment
{env_section}

IMPORTANT:
1. When using 'mobile_control', you MUST provide the specific `device_id` found in the Environment section above. Do not guess.
2. **Common Android Package Names**:
{self._build_package_list()}
3. **Common MacOS Application Names**:
{self._build_macos_app_list()}
4. **VERIFICATION**: After performing a UI action (click, type), you MUST use `verify_ui_state` to confirm the expected element or text is present. Do not assume success.

## 🔍 Discovery Insights (Active Awakening)
{spatial_awareness_section}

## Application Knowledge
{self._get_app_knowledge(topic)}

## Constraints
- You are a specialized sub-agent.
- Your mission is defined in the Mission Ticket.
- Focus ONLY on the mission.
- **MANDATORY VERIFICATION**: After *every* UI action (click, type, navigate), you MUST wait, then pull the latest UI state (e.g. `screenshot` or `dump_ax_tree`), and use `verify_ui_state` to confirm the expected element appeared before proceeding to the next step.
- Do not ask the user for clarification unless instructed by a specific protocol.
- You are STATELESS. You do not remember previous interactions.

{self._build_clipboard_section()}

{sandbox_footer}
"""

    def build_mission_message(self) -> str:
        """Constructs the user message that initiates the task."""
        topic = self.ticket.get("topic") or "General Task"
        criteria = "\n".join([f"- {c}" for c in self.ticket.get("acceptance_criteria", [])])

        # Add parameter context if available
        params = self.ticket.get("parameters", {})
        param_context = ""
        if params:
            param_context = "\n**Execution Parameters**:\n" + "\n".join([f"- {k}: {v}" for k, v in params.items()])

        return f"""### MISSION TICKET
**Goal**: {topic}

**Acceptance Criteria**:
{criteria}
{param_context}

Please execute this mission now. Use your tools."""

    def _build_package_list(self) -> str:
        """Helper to format package names for the prompt."""
        if not self.known_packages:
            return "   (No common packages recorded yet. Use 'mobile_control(action=\"list_apps\")' to identify them.)"

        lines = []
        for name, pkg in self.known_packages.items():
            lines.append(f"   - {name}: `{pkg}`")
        return "\n".join(lines)

    def _build_macos_app_list(self) -> str:
        """Helper to format MacOS app names for the prompt."""
        if not self.known_macos_apps:
            return "   (No common MacOS apps recorded yet. Use 'desktop_control(action=\"list_apps\")' to identify them.)"

        lines = []
        for name, app in self.known_macos_apps.items():
            lines.append(f"   - {name}: `{app}`")
        return "\n".join(lines)

    def _get_app_knowledge(self, topic: str) -> str:
        """
        Injects specific Expert Guides based on retrieved skills, or the Zero-SOP Fallback protocol.
        """
        if not self.skills:
            return """
### ⚠️ [ZERO-SOP FALLBACK: AUTONOMOUS EXPLORATION PROTOCOL] ⚠️
WARNING: There is no predefined Standard Operating Procedure (SOP) available for this task in this environment.

**AUTONOMOUS EXPLORATION INSTRUCTIONS:**
Because you lack a trusted SOP, proceed with visual exploration. 
You are permitted to autonomously explore and visually navigate the UI to achieve this goal.

Your workflow MUST be:
1. **Observe**: Take a screenshot.
2. **Analyze**: Use `analyze_image` or Atlas to find target elements.
3. **Act**: Execute a *single* `desktop_control` or `mobile_control` action.
4. **Verify**: Use `verify_ui_state` to confirm the screen changed as expected.
Repeat this cycle. Do not guess coordinates blindly.

"""

        knowledge_blocks = []
        for i, skill in enumerate(self.skills):
            # The first skill is usually the exact or fuzzy match which triggered the eager load
            is_primary = (i == 0)

            header = "### 🚨 [ACTIVE MISSION SOP]" if is_primary else "### 📘 Related Reference SOP"

            block = f"{header}: {skill.name}\n"

            if is_primary:
                block += "You MUST treat the following instructions as a strict state-machine. Read Phase 1. Execute. Verify. Only proceed to Phase 2 upon success.\n\n"

            if skill.description:
                block += f"**Description**: {skill.description}\n"

            if skill.instructions:
                block += f"**Expert Guide (操作指南)**:\n{skill.instructions}\n"

            knowledge_blocks.append(block)

        return "\n".join(knowledge_blocks)

    def _build_sandbox_footer(self) -> str:
        return """## SANDBOX PROTOCOL
- You have limited tools. Do not hallucinate tools you don't have.
- You cannot speak to the user.
- Provide a structured final report when done."""

    def _build_clipboard_section(self) -> str:
        """
        Injects the Workspace Clipboard (Short-term memory) into the prompt.
        """
        if not self.clipboard:
            return ""

        blocks = [
            "## WORKSPACE CLIPBOARD (Short-term memory)",
            "The following items have been stashed for your session.",
            "**Use these to transfer data between steps or applications.**\n"
        ]

        for idx, item in enumerate(self.clipboard):
            content = item.get("content", "")
            mime_type = item.get("mime_type", "text/plain")
            metadata = item.get("metadata", {})

            block = f"### Item {idx + 1} ({mime_type})\n"
            if metadata:
                meta_str = ", ".join([f"{k}: {v}" for k, v in metadata.items()])
                block += f"*Metadata*: {meta_str}\n"

            block += f"```\n{content}\n```\n"
            blocks.append(block)

        return "\n".join(blocks)
