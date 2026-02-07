from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.system import SystemConfigService


class DeveloperPromptBuilder:
    def __init__(self, state: AgentState, context: dict, project_id: int):
        self.state = state
        self.context = context
        self.project_id = project_id

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

"""
        return base_prompt
