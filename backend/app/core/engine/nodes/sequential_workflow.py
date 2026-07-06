"""
SequentialWorkflowNode - State-machine node for multi-skill sequential execution.
"""

import copy
import logging
from typing import Any

from app.core.config import settings
from app.core.engine import get_default_engine
from app.core.engine.message.utils import get_message_text
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.prompts import WorkerPromptBuilder
from app.core.engine.nodes.utils import resolve_is_subtask
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.sub_schemas import WorkflowStepResult
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class SequentialWorkflowNode(BaseAgentNode):
    """
    Executes a sequential multi-skill workflow one step per graph invocation.
    """

    def __init__(self):
        super().__init__(node_name="SequentialWorkflow", max_steps=1)

    async def __call__(self, state: AgentState, config: dict) -> StateUpdate:
        """Execute the next step of the sequential workflow."""
        plan = state.workflow_plan or []
        step_index = state.workflow_step_index or 0
        results = list(state.workflow_results or [])

        if step_index >= len(plan):
            logger.info(f"[SequentialWorkflow] All {len(plan)} steps completed.")
            return StateUpdate(
                messages=[{"role": "assistant", "content": f"Completed {len(plan)} step(s)."}],
                next_node=RoutingTarget.FINISH,
            )

        skill = plan[step_index]
        is_last = step_index == len(plan) - 1
        skill_name = getattr(skill, 'name', str(skill))
        logger.info(f"[SequentialWorkflow] Step {step_index + 1}/{len(plan)}: {skill_name}")

        execution_ticket = state.ticket
        if not execution_ticket:
            logger.error("[SequentialWorkflow] Missing execution ticket")
            return StateUpdate(
                messages=[{"role": "assistant", "content": "Sequential workflow failed: missing ticket.", "additional_kwargs": {"is_error": True}}],
                next_node=RoutingTarget.SUPERVISOR,
            )

        agent_config = execution_ticket.agent_config
        role_name = agent_config.role_name if agent_config else "Worker"

        step_ticket = copy.deepcopy(execution_ticket)
        step_ticket.skill_ids = [getattr(skill, "id")] if getattr(skill, "id", None) else None
        step_ticket.topic = f"Step {step_index + 1}: {skill_name}"

        prompt_builder = WorkerPromptBuilder(
            agent_config=agent_config,
            blackboard=state,
            skills=[skill] if not isinstance(skill, list) else skill,
            ticket=step_ticket,
            focus_paths=[],
            plan=state.structured_plan or state.current_plan,
        )
        system_prompt = await prompt_builder.build(config)

        prev_output = results[-1].output if results else ""
        mission_msg = prompt_builder.build_mission_message(
            session_goal=state.session_goal,
            previous_output=prev_output,
        )
        messages = [{"role": "user", "content": mission_msg}]

        from app.core.monitoring.activity import activity_monitor
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="EXECUTING",
            task_name=f"Workflow Step {step_index + 1}/{len(plan)}",
            task_status=f"Executing skill: {skill_name}"
        )

        worker_state = state.model_copy(update={"messages": messages})
        engine = get_default_engine()

        try:
            is_subtask = resolve_is_subtask(state)
            model = config.get("configurable", {}).get("model")
            engine_result = await engine.run_node(
                state=worker_state,
                config=config,
                system_prompt=system_prompt,
                tools=await self.get_tools(state),
                name=f"Worker-{role_name}-Step{step_index + 1}",
                max_steps=1 if is_subtask else settings.WORKER_AGENT_MAX_STEPS,
                is_subtask=is_subtask,
                node_source="sequential_workflow",
                model=model,
            )
        except (ValueError, RuntimeError, OSError) as e:
            logger.error(f"[SequentialWorkflow] Step {step_index + 1} failed: {e}")
            return StateUpdate(
                messages=[{"role": "assistant", "content": f"Workflow failed at step {step_index + 1}: {e}", "additional_kwargs": {"is_error": True, "error_type": "workflow_step_exception"}}],
                next_node=RoutingTarget.SUPERVISOR,
                workflow_results=results + [
                    WorkflowStepResult(
                        skill_id=getattr(skill, "id", None),
                        skill_name=skill_name,
                        output=str(e),
                        status="failed",
                    )
                ],
            )

        if engine_result.messages:
            last_msg = engine_result.messages[-1]
            step_output = get_message_text(last_msg) if last_msg.get("role") == "assistant" else ""
        else:
            step_output = ""

        if "[ERROR:" in step_output or step_output.strip().startswith("Error:"):
            logger.error(f"[SequentialWorkflow] Step {step_index + 1} returned error")
            results.append(WorkflowStepResult(
                skill_id=getattr(skill, "id", None),
                skill_name=skill_name,
                output=step_output,
                status="failed",
            ))
            return StateUpdate(
                messages=[{"role": "assistant", "content": f"Workflow failed at step {step_index + 1}/{len(plan)}: {skill_name}\n\n{step_output}", "additional_kwargs": {"is_error": True, "error_type": "workflow_step_failed"}}],
                next_node=RoutingTarget.SUPERVISOR,
                workflow_results=results,
            )

        results.append(WorkflowStepResult(
            skill_id=getattr(skill, "id", None),
            skill_name=skill_name,
            output=step_output,
            status="success",
        ))

        if is_last:
            logger.info("[SequentialWorkflow] Final step complete. Routing to FINISH.")
            return StateUpdate(
                messages=[{"role": "assistant", "content": f"Completed {len(plan)} step(s)."}],
                next_node=RoutingTarget.FINISH,
                workflow_results=results,
                workflow_step_index=step_index + 1,
            )

        return StateUpdate(
            messages=[{"role": "assistant", "content": f"Step {step_index + 1} complete."}],
            next_node=RoutingTarget.SEQUENTIAL_WORKFLOW,
            workflow_results=results,
            workflow_step_index=step_index + 1,
        )

    async def get_tools(self, state: AgentState) -> list[Any]:
        return await tool_manager.get_node_tools("worker", state)


sequential_workflow_node = SequentialWorkflowNode()
