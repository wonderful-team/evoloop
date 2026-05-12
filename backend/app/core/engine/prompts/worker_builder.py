import logging
from typing import Any

from app.core.context import ContextManager, plugin_registry
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.utils import render_template

from .utils import (
    get_mapped_cwd,
    get_sandbox_mode,
    read_project_profile,
    to_template_context,
)

logger = logging.getLogger(__name__)


class WorkerPromptBuilder:
    """
    Constructs the system prompt for dynamic, ephemeral sub-agents via Jinja2.
    """
    def __init__(
        self,
        agent_config: AgentRuntimeConfig | None,
        blackboard: BlackboardState | dict,
        skills: list = None,
        ticket: ExecutionTicket | None = None,
        focus_files: list = None,
        plan: dict | str = None
    ):
        self.agent_config = agent_config
        self.blackboard = blackboard
        self.skills = skills or []
        if isinstance(blackboard, dict):
            self.clipboard = blackboard.get("clipboard", [])
        else:
            self.clipboard = blackboard.clipboard if blackboard else []
        self.ticket = ticket
        self.focus_files = focus_files or []
        self.plan = plan

    async def build(self, config: Any = None) -> str:
        """Constructs the STATIC system prompt using Jinja2 templating.

        This part MUST be static for the duration of a session to trigger caching.
        Dynamic context (blackboard, telemetry, memory) is now moved to build_mission_message().
        """
        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        mode = get_sandbox_mode()

        # Read PROJECT.md if exists (static for the session)
        project_profile = read_project_profile(ctx.working_directory, "[WorkerPrompt]")

        # Static Sys Info (Project identity only)
        sys_info = {
            "is_global_mode": ctx.project_id == 0 or ctx.project_id is None,
            "project_concepts": ctx.metadata.get("project_concepts", ""),
            "project_profile": project_profile,
            "cwd": get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", "")),
        }

        # Protocol flags based on authorized tools (Static for the node)
        authorized_tools = self.agent_config.tools if self.agent_config else []
        has_desktop_tool = any(t in authorized_tools for t in ["desktop_control", "open_app"])
        has_mobile_tool = any(t in authorized_tools for t in ["mobile_control", "list_devices"])
        has_browser_tool = "browser_control" in authorized_tools

        logger.info(f"[WorkerPromptBuilder] Static Protocol flags: "
                   f"browser={has_browser_tool}, desktop={has_desktop_tool}, mobile={has_mobile_tool}")

        # Static Feature Check
        has_interactive_charts = False
        try:
            from app.core.evocloud import evocloud_manager
            from app.services.benefit_service import benefit_service
            token = await evocloud_manager.get_token()
            member_id_str = ctx.user_id
            if token and member_id_str:
                member_id = int(member_id_str)
                has_interactive_charts = await benefit_service.has_benefit(
                    member_id, "interactive_charts", token
                )
        except Exception as e:
            logger.debug(f"[WorkerPrompt] Benefit check failed: {e}")

        template_vars = {
            "project_id": ctx.project_id,
            "sys_info": sys_info,
            "sandbox_mode": mode,
            "role_name": self.agent_config.role_name if self.agent_config else "Specialist",
            "instructions": self.agent_config.system_instructions if self.agent_config else "Execute the assigned task accurately.",
            "has_android": ctx.metadata.get("has_android", False),
            "is_subtask": self.agent_config.is_subtask if self.agent_config else False,
            "has_desktop_tool": has_desktop_tool,
            "has_mobile_tool": has_mobile_tool,
            "has_browser_tool": has_browser_tool,
            "has_interactive_charts": has_interactive_charts,
        }

        return render_template("core/engine/worker.prompt.j2", **to_template_context(template_vars))

    def build_mission_message(
        self,
        environment_block: str = "",
        cwd: str = "",
        telemetry: dict = None,
        memory: dict = None,
        plan: Any = None,
        session_goal: str | None = None,
        previous_output: str = "",
    ) -> str:
        """Constructs the USER message (Mission Ticket) for the Worker.

        DYNAMIC CONTEXT:
        All items that change every turn are injected here to ensure
        the System Prompt remains stable and cacheable.
        """
        ctx = ContextManager.current()

        topic = (self.ticket.topic if self.ticket else None) or session_goal

        template_vars = {
            "topic": topic,
            "acceptance_criteria": self.ticket.acceptance_criteria if self.ticket else [],
            "parameters": self.ticket.parameters if self.ticket else {},
            "is_subtask": self.agent_config.is_subtask if self.agent_config else False,
            "focus_files": self.focus_files,
            "workflow_context": self.ticket.workflow_context if self.ticket else None,
            "cwd": cwd,
            "environment_block": environment_block,
            "telemetry": telemetry or {},
            "memory": memory or {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
            },
            "blackboard": self.blackboard,
            "clipboard": self.clipboard,
            "plan": plan or self.plan,
            "macro_goal": session_goal,
            "previous_output": previous_output,
        }
        return render_template("core/engine/fragments/worker_mission_ticket.j2", **to_template_context(template_vars))

    def _prepare_knowledge_blocks(self) -> list[str]:
        """
        Prepare knowledge blocks for all skills.

        Uses a single template render with the knowledge_blocks_wrapper.j2
        template for efficiency, then splits the result into individual blocks.

        Returns:
            List of rendered knowledge block strings
        """
        if not self.skills:
            return []

        try:
            # Render all blocks in a single template call for efficiency
            rendered = render_template(
                "core/engine/fragments/knowledge_blocks_wrapper.j2",
                skills=self.skills,
                is_subtask=self.agent_config.is_subtask if self.agent_config else False
            )

            # Split by double newline to get individual blocks
            blocks = [b.strip() for b in rendered.split('\n\n\n') if b.strip()]
            return blocks or [rendered.strip()]

        except Exception as e:
            logger.error(f"Error rendering Knowledge Blocks: {e}")
            # Fallback: render each skill individually
            blocks = []
            for i, skill in enumerate(self.skills):
                block = render_template(
                    "core/engine/fragments/knowledge_block.j2",
                    skill=skill,
                    is_primary=(i == 0),
                    is_subtask=self.agent_config.is_subtask if self.agent_config else False
                )
                blocks.append(block)

            return blocks
