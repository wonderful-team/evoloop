import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.system import SystemConfigService

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
        
        from app.domain.environment.prompt_utils import build_environment_prompt, detect_platform_relevance
        
        # Detect Platform Relevance to avoid context explosion
        platform_relevance = detect_platform_relevance(self.state.get("messages", []))
        
        # Inject environment awareness from awakening system
        env_section = build_environment_prompt(relevance=platform_relevance)
        
        # Skills as Knowledge injection
        skills_section = self._build_skills_section()
        
        base_prompt = f"""You are an expert **Full-Stack Developer** agent.
Your goal is to complete the assigned task by writing code, running commands, and verifying the output.

### 1. CAPABILITIES
- **Code**: You can read/write files. Always read specific files before editing.
- **Test**: You can run shell commands (pytest, npm test, etc.) to verify your changes.
- **Structure**: You have access to the file tree.
- **Desktop Control**: You can interact with the MacOS desktop (screenshot, click, type).
- **Mobile Control**: You can interact with connected Android devices via ADB.

### 2. EXECUTION PROTOCOL (The Inner Loop)
You are responsible for the ENTIRE lifecycle of this task. Do not ask for permission to run tests.
1. **Analyze**: Understand the request and the file structure.
2. **Execute**: Make necessary code changes.
3. **Verify**: IMMEDIATEY run a test or a command to verify your changes worked.
    - If it fails -> Fix it -> Verify again.
    - If it passes -> You are done.

### 3. ENVIRONMENT
- Language: {user_lang}
{env_section}
- Project Structure:
{tree}

### 4. CRITICAL RULES
- **No Hallucination**: Do not reference files that are not in the tree.
- **Verification**: NEVER finish a task without running at least one verification command (e.g. `ls`, `grep`, `pytest`, `node script.js`).
- **Atomic Edits**: When editing, use `replace_file_content` for small changes or `write_to_file` for new files.
- **Device Awareness**: When using `mobile_control`, always specify the correct `device_id` from the connected devices list above.

{skills_section}
"""
        return base_prompt

    def _build_skills_section(self) -> str:
        """
        构建技能知识注入章节 (Skills as Knowledge)。
        
        将已习得技能的 instructions (心法/SOP) 注入到 System Prompt，
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
