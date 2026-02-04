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
        
        # Inject environment awareness from awakening system
        env_section = self._build_environment_section()
        
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

    def _build_environment_section(self) -> str:
        """Build environment awareness section from awakened state."""
        try:
            from app.core.environment import get_awakened_state
            state = get_awakened_state()
            
            if not state:
                return "- **Environment**: Not yet awakened (use default settings)"
            
            sections = []
            
            # MacOS info
            if state.macos:
                sections.append(f"- **Host**: {state.macos.model} ({state.macos.cpu}), macOS {state.macos.os_version}")
            
            # Android devices (critical for mobile_control)
            if state.android_devices:
                sections.append("- **Connected Android Devices**:")
                for dev in state.android_devices:
                    emoji = "✅" if dev.is_reachable else "⚠️"
                    sections.append(f"  - {emoji} `{dev.device_id}`: {dev.model} (Android {dev.os_version}), Battery: {dev.battery_percent}%")
            else:
                sections.append("- **Connected Android Devices**: None (mobile_control will fail)")
            
            # Network
            if state.network:
                net_status = "Online" if state.network.internet_connected else "Offline"
                sections.append(f"- **Network**: {net_status}")
            
            return "\n".join(sections)
            
        except Exception:
            return "- **Environment**: Unable to retrieve (use default settings)"
