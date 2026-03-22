import asyncio
import logging
from typing import Any, Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from app.utils import ControllerResponse, SkillResponse, render_template

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.bash",
    name_map={"zh": "执行命令", "en": "Execute Bash"}
)
async def bash(command: str) -> str:
    """
    Run a shell command (e.g., 'pytest', 'npm install', 'ls -la').

    This is your primary tool for navigating the OS, running scripts, building projects,
    and executing standard operating procedures.

    WARNING: Use dedicated tools for standard operations when available:
    - Version Control -> Use `manage_git` tools.
    - File Editing -> Use `edit_file` / `write_file`.
    - File Reading -> Use `read_file`.

    Only use this for execution tasks like running tests, builds, or scripts.
    """
    logger.info(f"Execution [Bash]: {command}")

    try:
        from app.core.execution import SandboxFactory

        sandbox = SandboxFactory.get_sandbox()

        # Run via Sandbox (handles stateful CWD/ENV if using LocalSandbox)
        stdout, stderr, returncode = await asyncio.to_thread(sandbox.run_command, command)
        
        status_msg = "Command Succeeded." if returncode == 0 else f"Command Failed (Exit Code {returncode})."
        output_details = render_template(
            "report/tool_outputs.prompt.j2",
            stdout=stdout,
            stderr=stderr,
            returncode=returncode
        )
        
        if returncode == 0:
            return ControllerResponse.success(status_msg, details=output_details)
        else:
            return ControllerResponse.error(status_msg, details=output_details)

    except Exception as e:
        return ControllerResponse.error("Execution Error", details=str(e))


@evoloop_tool(
    is_pollable=True,
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.run_macro",
    name_map={"zh": "执行宏", "en": "Run Macro"}
)
async def run_macro(
    skill_name: str | None = None,
    skill_id: int | None = None,
    params: dict[str, Any] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Execute a learned macro skill by name or ID.

    Use this when you know a specific learned macro exists and you want to run it
    deterministically. This is more efficient and reliable than recreating steps
    from scratch using browser_control / desktop_control / mobile_control.

    WHEN TO USE:
    - After `search_skills` returns a match with `execution_mode = "deterministic"`.
    - When the user explicitly asks you to replay a recorded skill.
    - When you want to repeat a previously successful multi-step automation.

    WHEN NOT TO USE:
    - For open-ended tasks where adaptive reasoning is required (use tools directly).
    - When the skill returns `execution_mode = "agentic"` (follow its `markdown_sop` instead).

    Args:
        skill_name: Exact name of the skill to execute. Perform a case-insensitive DB lookup.
                    Use the name returned by `search_skills`.
        skill_id:   Skill ID (integer primary key). Use if you have the exact ID from
                    `search_skills`. Takes precedence over skill_name when both are given.
        params:     Runtime parameter dict to inject into the macro steps,
                    e.g. {"query": "iPhone 15", "target_url": "https://example.com"}.
                    These map to `{{parameters.query}}` placeholders in the macro steps.
        thread_id:  The current conversation thread ID (injected automatically by the
                    framework; you do not need to pass this manually).

    Returns:
        A string summary of execution result, including extracted_data if any EXTRACT
        steps were present.

    Example:
        # After search_skills returns skill_id=42, execution_mode="deterministic":
        result = await run_macro(skill_id=42, params={"keyword": "机器学习"})
    """
    from app.core.execution.macro.service import MacroService
    from app.infrastructure.database.sql.database import session_scope
    from app.models.learning import LearnedSkill
    from sqlalchemy import select, func

    # 1. Resolve thread_id from LangGraph config
    thread_id = "default"
    if config:
        cfgable = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {})
        thread_id = cfgable.get("thread_id", "default") or "default"

    # 2. Load skill from DB
    skill = None
    try:
        async with session_scope() as db:
            if skill_id is not None:
                skill = await db.get(LearnedSkill, skill_id)
            elif skill_name:
                stmt = select(LearnedSkill).where(
                    func.lower(LearnedSkill.name) == skill_name.lower(),
                    LearnedSkill.is_active == True,
                )
                result = await db.execute(stmt)
                skill = result.scalar_one_or_none()
    except Exception as e:
        return ControllerResponse.error(
            f"Failed to look up skill '{skill_name or skill_id}'",
            details=str(e)
        )

    if not skill:
        identifier = f"id={skill_id}" if skill_id else f"name='{skill_name}'"
        return ControllerResponse.not_found(identifier, item_type="skill")

    # 3. Parse and validate macro script (now stored as YAML string)
    macro_script = None
    if skill.macro_script:
        from app.utils.yaml import macro_from_yaml
        try:
            macro_script = macro_from_yaml(skill.macro_script)
        except Exception as e:
            return ControllerResponse.error(
                f"Failed to parse macro YAML for skill '{skill.name}'",
                details=str(e)
            )

    if not macro_script or not isinstance(macro_script, list) or len(macro_script) == 0:
        mode = skill.execution_mode or "agentic"
        return ControllerResponse.error(
            f"Skill '{skill.name}' has no macro script.",
            details=f"Mode: {mode}\nInstructions: {skill.instructions or 'None'}",
            note="This skill requires agentic execution."
        )

    if skill.execution_mode != "deterministic":
        return ControllerResponse.error(
            f"Skill '{skill.name}' is not in deterministic mode.",
            details=f"Current mode: {skill.execution_mode}\nInstructions: {skill.instructions or 'None'}",
            note="Follow the SOP instructions above instead."
        )

    logger.info(
        f"[run_macro] Executing skill '{skill.name}' (id={skill.id}) "
        f"with {len(macro_script)} steps, params={params}"
    )
    
    # Pass metadata for the event advisor to use
    execution_params = params.copy() if params else {}
    execution_params["_skill_id"] = skill.id
    execution_params["_skill_name"] = skill.name
    
    result = await MacroService.run(
        thread_id=thread_id,
        script_input=macro_script,
        params=execution_params,
        skill=skill,
    )

    # 5. Format result using SkillResponse for consistency
    if result.get("success"):
        return SkillResponse.success(skill.name, result.get("extracted_data"))
    else:
        return SkillResponse.error(
            skill.name,
            result.get("message", "Unknown error"),
            fallback_context=result.get("fallback_context"),
            suggestions=result.get("suggestions", [])
        )
