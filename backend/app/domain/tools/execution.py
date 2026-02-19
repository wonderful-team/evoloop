import asyncio
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def run_command(command: str) -> str:
    """
    Run a shell command (e.g., 'pytest', 'npm install').

    WARNING: Use dedicated tools for standard operations:
    - Version Control -> Use `git_*` tools.
    - File Editing -> Use `edit_file` / `write_file_content`.
    - File Reading -> Use `read_file`.

    Only use this for execution tasks like running tests, builds, or scripts.
    """
    logger.info(f"Tester [Running]: {command}")

    # Security Warning: This is a high-risk tool.
    # In production, this should be sandboxed (Docker/gVisor).
    # For this local assistant, we assume trust.

    try:
        from app.core.execution import SandboxFactory

        sandbox = SandboxFactory.get_sandbox()

        # Run via Sandbox
        stdout, stderr, returncode = await asyncio.to_thread(sandbox.run_command, command)

        output = ""
        if stdout:
            output += f"STDOUT:\n{stdout}\n"
        if stderr:
            output += f"STDERR:\n{stderr}\n"

        if returncode == 0:
            return f"Command Succeeded.\n{output}"
        else:
            return f"Command Failed (Exit Code {returncode}).\n{output}"

    except Exception as e:
        return f"Execution Error: {str(e)}"


#@tool
async def execute_learned_skill(skill_name: str, params: dict = None) -> str:
    """
    [DEPRECATED] Execute a previously learned or imported skill by its name.
    
    NOTE: Skills should be injected as knowledge context in system prompts,
    not called as executable tools. This function is kept for backward compatibility
    with existing Agent YAML configurations.

    Args:
        skill_name: The exact name of the skill to execute (e.g., 'algorithmic-art').
        params: Key-value parameters required by the skill.
    """
    from app.core.learning.skill_executor import SkillExecutor, build_skill_tool_registry
    from app.core.learning.discovery import skill_discovery
    from app.core.context.manager import ContextManager
    
    logger.warning(
        f"[DEPRECATED] execute_learned_skill called for '{skill_name}'. "
        "Skills should be injected as knowledge context, not called as tools. "
        "This violates the Skills != Tools principle."
    )
    
    # 1. Resolve Skill ID
    match = await skill_discovery.match(skill_name, threshold=0.9)
    if not match:
        return f"Error: Skill '{skill_name}' not found or matched with low confidence."
    
    # 2. Prepare Executor
    ctx = ContextManager.current()
    executor = SkillExecutor(config={"configurable": {"thread_id": ctx.thread_id}})
    
    # 3. Handle registry (re-use current tool environment)
    tool_registry = build_skill_tool_registry()
    
    # 4. Execute
    success, summary = await executor.execute_skill(
        skill_id=match.skill_id,
        params=params or {},
        tool_registry=tool_registry
    )
    
    if success:
        return f"Skill '{skill_name}' executed successfully.\nSummary:\n{summary}"
    else:
        return f"Skill '{skill_name}' failed.\nError/Summary:\n{summary}"
