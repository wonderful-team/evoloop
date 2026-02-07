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
        known_macos_apps: dict[str, str] = None
    ):
        self.agent_config = agent_config
        self.ticket = ticket
        self.skills = skills or []
        self.known_packages = known_packages or {}
        self.known_macos_apps = known_macos_apps or {}

    def build(self, config: RunnableConfig | None = None) -> str:
        """Constructs the full system prompt."""
        role_name = self.agent_config.get("role_name", "Specialist")
        instructions = self.agent_config.get("system_instructions", "You are a helpful assistant.")
        
        from app.domain.environment.prompt_utils import build_environment_prompt
        
        # For specialists, we use the topic/instructions as relevance context
        # We don't want them getting overwhelmed, so we use a very targeted relevance
        topic = self.ticket.get("topic", "").lower() + " " + instructions.lower()
        
        has_android = any(k in topic for k in ["android", "adb", "mobile", "phone"])
        has_macos = any(k in topic for k in ["mac", "desktop", "macos", "apple"])
        
        relevance = "auto"
        if has_android and not has_macos: relevance = "android"
        elif has_macos and not has_android: relevance = "macos"
        elif has_android and has_macos: relevance = "both"
        
        env_section = build_environment_prompt(relevance=relevance)

        # Sandbox Warning
        sandbox_footer = self._build_sandbox_footer()

        return f"""## Your Role: {role_name}
{instructions}

## Environment
{env_section}

IMPORTANT:
1. When using 'mobile_control', you MUST provide the specific `device_id` found in the Environment section above. Do not guess.
2. **Common Android Package Names**:
{self._build_package_list()}
3. **Common MacOS Application Names**:
{self._build_macos_app_list()}

## 🔍 Discovery Insights (Active Awakening)
{self._build_discovery_section()}

## Application Knowledge
{self._get_app_knowledge(topic)}

## Constraints
- You are a specialized sub-agent.
- Your mission is defined in the Mission Ticket.
- Focus ONLY on the mission.
- **VERIFY YOUR ACTIONS**: After opening an app, **WAIT 5 SECONDS**, then take a screenshot to confirm.
- Do not ask the user for clarification. If you are stuck, report the error.
- You are STATELESS. You do not remember previous interactions.

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

    def _build_discovery_section(self) -> str:
        """Helper to build the discovery insights section."""
        from app.domain.environment import get_awakened_state
        state = get_awakened_state()
        if not state or not state.discovery_report:
            return "No recent active discovery findings."

        report = state.discovery_report
        lines = []
        
        # New Apps
        all_new_apps = []
        for device_serial, discovery in report.get("android", {}).items():
            if discovery.get("new_apps_found"):
                all_new_apps.extend(discovery["new_apps_found"])
        
        if all_new_apps:
            lines.append(f"- **New Apps Found (Android)**: {', '.join(all_new_apps[:5])}{'...' if len(all_new_apps) > 5 else ''}")
            lines.append("  *Action Tip*: These apps were just discovered on the device. I may need to explore them before performing complex tasks.")

        # Missing SOPs
        all_missing_sops = []
        for device_serial, discovery in report.get("android", {}).items():
            if discovery.get("missing_sops"):
                all_missing_sops.extend(discovery["missing_sops"])
        
        if all_missing_sops:
            lines.append(f"- **Missing SOPs for Key Apps**: {', '.join(set(all_missing_sops))}")
            lines.append("  *Warning*: I don't have expert guidance for these installed apps. Higher caution and initial exploration are required.")

        # UI Baselines
        verified_layouts = []
        if state and state.relevant_concepts:
            for c in state.relevant_concepts:
                if c.name.startswith("android_layout:"):
                    verified_layouts.append(c.name.split(":", 1)[1])
        
        if verified_layouts:
            lines.append(f"- **Verified UI Baselines**: {', '.join(verified_layouts)}")
            lines.append("  *Benefit*: I have already performed a silent probe of these apps. I possess their UI structure in my long-term memory.")

        # MacOS Verified
        macos_verified = report.get("macos", {}).get("verified_apps", [])
        if macos_verified:
            lines.append(f"- **MacOS Tools Verified**: {', '.join(macos_verified)}")

        return "\n".join(lines) if lines else "Environment state matches known knowledge base."

    def _get_app_knowledge(self, topic: str) -> str:
        """
        Injects specific Standard Operating Procedures (SOP) based on retrieved skills.
        """
        if not self.skills:
            return "No specific application SOP available. Rely on UI cues."

        knowledge_blocks = []
        for skill in self.skills:
            block = f"### 📘 Skill: {skill.name}\n"
            # Prefer description as the SOP text
            if skill.description:
                block += f"{skill.description}\n"
            
            # If trigger patterns mention a package usage, highlight it
            # (Optional enhancement)
            
            knowledge_blocks.append(block)
        
        return "\n".join(knowledge_blocks)

    def _build_sandbox_footer(self) -> str:
        return """## SANDBOX PROTOCOL
- You have limited tools. Do not hallucinate tools you don't have.
- You cannot speak to the user.
- Provide a structured final report when done."""
