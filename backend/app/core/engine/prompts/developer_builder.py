import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class DeveloperPromptBuilder:
    def __init__(self, state: AgentState, context: dict, project_id: int, skills: list[Any] | None = None):
        self.state = state
        self.context = context
        self.project_id = project_id
        self.skills = skills or []

    def build(self, config: RunnableConfig) -> str:
        """
        Builds the system prompt for the Developer Agent.
        """
        user_lang = SystemConfigService.get_value("LANGUAGE", "en")
        tree = self.context.get("project_structure", "")
        
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

        base_prompt = f"""You are an expert **Universal Specialist** agent (Developer & Operator).
Your goal is to complete the assigned task by executing the correct specialized tools (e.g., coding, shell, web automation, mobile, desktop).

### 1. CAPABILITIES
- **Code**: You can read/write files. Always read specific files before editing.
- **Verification**: You can run shell commands to verify changes or observe environment states.
- **Structure**: You have access to the file tree.
- **Desktop Control**: You can interact with the MacOS desktop (screenshot, click, type).
- **Mobile Control**: You can interact with connected Android devices via ADB.

### 2. EXECUTION PROTOCOL (The Inner Loop)
You are responsible for the ENTIRE lifecycle of this task. Do not ask for permission to use your tools.
1. **Analyze**: Understand the request, constraints, and environment.
2. **Execute**: Take the necessary actions using your tools.
3. **Verify**: IMMEDIATELY use verification tools to ensure your actions succeeded.
    - If it fails -> Fix it -> Verify again.
    - If it passes -> You are done.

### 3. ENVIRONMENT
- Language: {user_lang}
{env_section}
- Project Structure:
{tree}

### 4. CRITICAL RULES
- **No Hallucination**: Do not reference files that are not in the tree (unless searching the web).
- **Verification**: NEVER finish a technical/operational task without verifying your work (e.g., running tests, viewing UI, reading logs). For theoretical questions or online research, this is not required.
- **Atomic Edits**: When editing local files, use `replace_file_content` for small changes or `write_to_file` for new files.
- **Device Awareness**: When using `mobile_control`, always specify the correct `device_id` from the connected devices list above.

{skills_section}
"""
        return base_prompt

    def _build_skills_section(self) -> str:
        """
        构建技能知识注入章节 (Skills as Knowledge)。
        
        注入已知技能的心法 (Expert Skill Guide) 的 System Prompt，
        让 Agent 能以专家指南的形式参考这些知识来指导工具执行。
        """
        if not self.skills:
            return ""

        blocks = ["### 5. EXPERT GUIDANCE (SKILLS)",
                   "The following are expert guides for tasks you may encounter.",
                   "**Use these as your strategy reference when executing with your tools.**\n"]

        for skill in self.skills:
            block = f"#### 📘 Skill: {skill.name}\n"
            
            if skill.description:
                block += f"**Description**: {skill.description}\n"
            
            if skill.instructions:
                block += f"**Expert Guide (心法)**:\n{skill.instructions}\n"
            
            # Include trigger patterns as usage hints
            if skill.trigger_patterns:
                try:
                    triggers = json.loads(skill.trigger_patterns)
                    if triggers:
                        block += f"**Trigger Patterns**: {', '.join(triggers[:3])}\n"
                except Exception:
                    pass

            blocks.append(block)

        return "\n".join(blocks)
