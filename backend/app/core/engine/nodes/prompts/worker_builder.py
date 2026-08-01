import logging
from typing import TYPE_CHECKING, Any

from jinja2 import TemplateError

from app.core.config import settings
from app.core.context import ContextManager, plugin_registry
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.utils.template import render_template

from .base_builder import BasePromptBuilder

if TYPE_CHECKING:
    from app.core.engine.state.base import AgentState

logger = logging.getLogger(__name__)


class WorkerPromptBuilder(BasePromptBuilder):
    """
    Constructs the system prompt for dynamic, ephemeral sub-agents via Jinja2.

    Worker receives skills ALREADY selected by the Supervisor (via ExecutionTicket.skill_ids).
    Therefore the Worker injects the FULL skill content (not an index) — the routing
    decision has already been made upstream. NLP skill indexing / lazy loading belongs
    to the Supervisor, not here.
    """

    def __init__(
        self,
        agent_config: AgentRuntimeConfig | None,
        blackboard: "AgentState",
        skills: list = None,
        ticket: ExecutionTicket | None = None,
        focus_paths: list = None,
        plan: dict | str = None,
    ):
        self.agent_config = agent_config
        self.blackboard = blackboard
        self.skills = skills or []
        if isinstance(blackboard, dict):
            self.clipboard = blackboard.get("clipboard", [])
        else:
            self.clipboard = blackboard.clipboard or []
        self.ticket = ticket
        self.focus_paths = focus_paths or []
        self.plan = plan

    async def build(self, config: Any = None) -> str:
        """Constructs the STATIC system prompt using Jinja2 templating.

        This part MUST be static for the duration of a session to trigger caching.
        Dynamic context (blackboard, telemetry, memory) is now moved to build_mission_message().
        """
        ctx = ContextManager.current()
        await plugin_registry.ahydrate_context(ctx)

        mode = self.get_sandbox_mode()

        # Read PROJECT.md if exists (static for the session)
        project_profile = self.read_project_profile(ctx.working_directory, "[WorkerPrompt]")

        # Read wiki index for prompt injection (project mode only)
        from app.core.engine.nodes.utils.node_utils import read_wiki_index

        wiki_index = await read_wiki_index(ctx.project_id)

        # Static Sys Info (Project identity only)
        sys_info = {
            "project_concepts": ctx.metadata.get("project_concepts", ""),
            "project_profile": project_profile,
            "wiki_index": wiki_index,
            "cwd": self.get_mapped_cwd(
                ctx.working_directory or ctx.metadata.get("cwd", "")
            ),
        }

        # Protocol flags based on the node's tool list (Static for the node)
        node_tools = self.agent_config.tools if self.agent_config else []
        has_desktop_tool = any(t in node_tools for t in ["desktop_control", "open_app"])
        has_mobile_tool = any(
            t in node_tools for t in ["mobile_control", "list_devices"]
        )
        has_browser_tool = "browser_control" in node_tools
        has_wiki_tools = any(
            t in node_tools
            for t in ["write_wiki_page", "edit_wiki_page", "save_concepts"]
        )

        logger.info(
            f"[WorkerPromptBuilder] Static Protocol flags: "
            f"browser={has_browser_tool}, desktop={has_desktop_tool}, mobile={has_mobile_tool}, wiki={has_wiki_tools}"
        )

        # Static Feature Check
        has_interactive_charts = False
        from app.core.evocloud import evocloud_manager
        from app.services.benefit_service import benefit_service

        token = await evocloud_manager.get_token()
        member_id = ctx.member_id
        if token and member_id:
            has_interactive_charts = await benefit_service.has_benefit(
                member_id, "interactive_charts", token
            )

        template_vars = {
            "project_id": ctx.project_id,
            "sys_info": sys_info,
            "sandbox_mode": mode,
            "multi_tenant_mode": settings.MULTI_TENANT_MODE,
            "role_name": self.agent_config.role_name if self.agent_config else "Specialist",
            "instructions": self.agent_config.system_instructions if self.agent_config else "Execute the assigned task accurately.",
            "has_android": ctx.metadata.get("has_android", False),
            "is_subtask": self.agent_config.is_subtask if self.agent_config else False,
            "has_desktop_tool": has_desktop_tool,
            "has_mobile_tool": has_mobile_tool,
            "has_browser_tool": has_browser_tool,
            "has_wiki_tools": has_wiki_tools,
            "has_interactive_charts": has_interactive_charts,
            "user_lang": self.get_user_lang(),
            "user_preferences": ctx.metadata.get("user_preferences", {}),
            "has_file_operations": True,
        }

        return render_template("core/engine/worker.prompt.j2", **self.to_template_context(template_vars))

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

        # Safely extract flat state properties
        if isinstance(self.blackboard, dict):
            shared_context = self.blackboard.get("shared_context", {})
            subtask_results = self.blackboard.get("subtask_results", [])
            metadata = self.blackboard.get("metadata", {})
        else:
            shared_context = self.blackboard.shared_context or {}
            subtask_results = self.blackboard.subtask_results or []
            metadata = self.blackboard.metadata or {}

        template_vars = {
            "topic": topic,
            "active_macros": ctx.metadata.get("active_macros", []) or [],
            "operation_map": ctx.metadata.get("operation_map", "") or "",
            "acceptance_criteria": self.ticket.acceptance_criteria if self.ticket else [],
            "parameters": self.ticket.parameters if self.ticket else {},
            "is_subtask": self.agent_config.is_subtask if self.agent_config else False,
            "focus_paths": self.focus_paths,
            "knowledge_blocks": self._prepare_knowledge_blocks(),
            "workflow_context": self.ticket.workflow_context if self.ticket else None,
            "cwd": cwd,
            "environment_block": environment_block,
            "telemetry": telemetry or {},
            "memory": memory or {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
            },
            "shared_context": shared_context,
            "subtask_results": subtask_results,
            "metadata": metadata,
            "clipboard": self.clipboard,
            "plan": plan or self.plan,
            "macro_goal": session_goal,
            "previous_output": previous_output,
            "historical_context": self.ticket.historical_context if self.ticket else None,
            "referenced_tech": self.ticket.referenced_tech if self.ticket else None,
        }
        return render_template("core/engine/fragments/worker_mission_ticket.j2", **self.to_template_context(template_vars))

    def _prepare_knowledge_blocks(self) -> list[str]:
        """
        Prepare knowledge blocks for all skills.

        Worker injects FULL skill content because the Supervisor has already
        selected which skills are relevant — there is no routing decision left
        for the Worker to make, so no need for a lightweight index.

        Uses a single template render with the knowledge_blocks.j2
        template for efficiency, then splits the result into individual blocks.
        """
        if not self.skills:
            return []

        try:
            rendered = render_template(
                "core/engine/fragments/knowledge_blocks.j2",
                skills=self.skills,
                is_subtask=self.agent_config.is_subtask if self.agent_config else False,
            )
            blocks = [b.strip() for b in rendered.split("\n\n\n") if b.strip()]
            return blocks or [rendered.strip()]
        except (ImportError, TemplateError) as e:
            logger.error(f"Error rendering Knowledge Blocks: {e}")
            blocks = []
            for i, skill in enumerate(self.skills):
                block = render_template(
                    "core/engine/fragments/skill_block.j2",
                    skill=skill,
                    is_primary=(i == 0),
                    is_subtask=self.agent_config.is_subtask if self.agent_config else False,
                )
                blocks.append(block)
            return blocks
