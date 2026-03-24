import os
import logging
from typing import Any

from app.core.config import settings
from app.core.context import ContextManager, plugin_registry
from app.utils import ControllerResponse, render_template

logger = logging.getLogger(__name__)


class WorkerPromptBuilder:
    """
    Constructs the system prompt for dynamic, ephemeral sub-agents via Jinja2.
    """
    def __init__(
        self,
        agent_config: dict,
        blackboard: dict,
        skills: list = None,
        ticket: dict = None,
        focus_files: list = None,
        plan: dict | str = None
    ):
        self.agent_config = agent_config
        self.blackboard = blackboard
        self.skills = skills or []
        self.clipboard = blackboard.get("clipboard", [])
        self.ticket = ticket or {}
        self.focus_files = focus_files or []
        self.plan = plan

    def build(self, config: Any = None) -> str:
        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        knowledge_blocks = self._prepare_knowledge_blocks()

        from app.core.environment import get_awakened_state
        state = get_awakened_state()
        telemetry_data = {}
        try:
            if state:
                telemetry_data = {
                    "android": [{"id": d.device_id, "reachable": d.is_reachable} for d in state.android_devices],
                    "macos": bool(state.macos),
                    "network": state.network.internet_connected if state.network else False
                }
        except Exception as e:
            logger.warning(f"[WorkerPrompt] Failed to fetch telemetry: {e}")

        # Environment Normalization (Docker Path Mapping)
        from .utils import get_mapped_cwd, get_sandbox_mode
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        mode = get_sandbox_mode()
        
        if mode == "docker":
            pass # Mapping already handled in get_mapped_cwd

        sys_info = {
            "cwd": actual_cwd,
            "is_global_mode": ctx.project_id == 0 or ctx.project_id is None,
            "project_concepts": ctx.metadata.get("project_concepts", ""),
        }

        template_vars = {
            "project_id": ctx.project_id,
            "sys_info": sys_info,
            "sandbox_mode": mode,
            "telemetry": telemetry_data,
            "blackboard": self.blackboard,
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
                "use_neo4j": settings.USE_NEO4J_MEMORY,
            },
            "role_name": self.agent_config.get("role_name", "Specialist"),
            "instructions": self.agent_config.get("system_instructions", "Execute the assigned task accurately."),
            "environment_block": ctx.environment_block,
            "knowledge_blocks": knowledge_blocks,
            "clipboard": self.clipboard,
            "has_android": ctx.metadata.get("has_android", False),
            "is_subtask": self.agent_config.get("is_subtask", False),
            "historical_context": self.ticket.get("historical_context") if self.ticket else None,
            "referenced_tech": self.ticket.get("referenced_tech") if self.ticket else None,
            "plan": self.plan,
        }

        try:
            return render_template("agents/worker.prompt.j2", **template_vars)
        except Exception as e:
            logger.error(f"Error rendering Worker template: {e}")
            return ControllerResponse.error("Worker Instruction Error", details=str(e))

    def build_mission_message(self) -> str:
        """Constructs the user message that initiates the task via Jinja2."""
        template_vars = {
            "topic": self.ticket.get("topic") or "General Task",
            "acceptance_criteria": self.ticket.get("acceptance_criteria", []),
            "parameters": self.ticket.get("parameters", {}),
            "is_subtask": self.agent_config.get("is_subtask", False),
            "focus_files": self.focus_files,
        }
        try:
            return render_template("fragments/mission_ticket.j2", **template_vars)
        except Exception as e:
            logger.error(f"Error rendering Mission Ticket: {e}")
            return ControllerResponse.error("Mission Ticket Error", details=str(e), note=template_vars['topic'])

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
                "fragments/knowledge_blocks_wrapper.j2",
                skills=self.skills,
                is_subtask=self.agent_config.get("is_subtask", False)
            )
            
            # Split by double newline to get individual blocks
            blocks = [b.strip() for b in rendered.split('\n\n\n') if b.strip()]
            return blocks or [rendered.strip()]
            
        except Exception as e:
            logger.error(f"Error rendering Knowledge Blocks: {e}")
            # Fallback: render each skill individually
            blocks = []
            for i, skill in enumerate(self.skills):
                try:
                    block = render_template(
                        "fragments/knowledge_block.j2",
                        skill=skill,
                        is_primary=(i == 0),
                        is_subtask=self.agent_config.get("is_subtask", False)
                    )
                    blocks.append(block)
                except Exception as inner_e:
                    logger.error(f"Error rendering individual skill block: {inner_e}")
                    blocks.append(f"SOP: {getattr(skill, 'name', 'Skill')}")
            return blocks
