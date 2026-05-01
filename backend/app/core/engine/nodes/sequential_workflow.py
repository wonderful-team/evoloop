"""
SequentialWorkflowNode - State-machine node for multi-skill sequential execution.

Replaces WorkerNode._execute_sequential_workflow to eliminate sub-engine recursion.
Each graph invocation executes exactly one skill step, leveraging LangGraph's
built-in checkpointing for resume-on-failure.
"""

import copy
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context import ContextManager
from app.core.engine import get_default_engine
from app.core.engine.message.utils import get_message_text
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.utils import resolve_is_subtask
from app.core.engine.prompts import WorkerPromptBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import WorkflowStepResult
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class SequentialWorkflowNode(BaseAgentNode):
    """
    Executes a sequential multi-skill workflow one step per graph invocation.

    Design note on message history:
    Each step receives ONLY a single HumanMessage (mission_msg) containing
    the previous step's output summary. The full ReAct history (tool calls,
    reasoning, intermediate results) from engine.run_node() is NOT appended
    to the main message history. Only a placeholder "Step N complete." is
    returned. This is intentional to prevent multi-step workflows from
    exploding the context window. Full details are preserved in
    blackboard.workflow_results.

    State persistence:
    - blackboard.workflow_plan: list of skill IDs/names
    - blackboard.workflow_step_index: current step (0-based)
    - blackboard.workflow_results: accumulated results
    """

    def __init__(self):
        super().__init__(node_name="SequentialWorkflow", max_steps=1)

    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
        """Execute the next step of the sequential workflow."""
        blackboard = state.blackboard
        if not blackboard:
            logger.error("[SequentialWorkflow] Missing blackboard")
            return StateUpdate(
                messages=[AIMessage(content="Sequential workflow failed: missing blackboard.", metadata={"is_error": True})],
                next_node=RoutingTarget.SUPERVISOR,
            )

        plan = blackboard.workflow_plan or []
        step_index = blackboard.workflow_step_index or 0
        results = list(blackboard.workflow_results or [])

        if step_index >= len(plan):
            # All steps completed
            logger.info(f"[SequentialWorkflow] All {len(plan)} steps completed.")
            return StateUpdate(
                messages=[AIMessage(content=f"Completed {len(plan)} step(s).")],
                next_node=RoutingTarget.FINISH,
                blackboard=blackboard,
            )

        skill = plan[step_index]
        is_last = step_index == len(plan) - 1
        skill_name = getattr(skill, 'name', str(skill))
        logger.info(f"[SequentialWorkflow] Step {step_index + 1}/{len(plan)}: {skill_name}")

        execution_ticket = blackboard.ticket
        if not execution_ticket:
            logger.error("[SequentialWorkflow] Missing execution ticket")
            return StateUpdate(
                messages=[AIMessage(content="Sequential workflow failed: missing ticket.", metadata={"is_error": True})],
                next_node=RoutingTarget.SUPERVISOR,
            )

        agent_config = execution_ticket.agent_config
        role_name = agent_config.role_name if agent_config else "Worker"

        # Build step-specific ticket
        step_ticket = copy.deepcopy(execution_ticket)
        step_ticket.skill_id = getattr(skill, "id", None)
        step_ticket.topic = f"Step {step_index + 1}: {skill_name}"

        # Build prompt
        ctx = ContextManager.current()
        prompt_builder = WorkerPromptBuilder(
            agent_config=agent_config,
            blackboard=blackboard,
            skills=[skill] if not isinstance(skill, list) else skill,
            ticket=step_ticket,
            focus_files=[],  # focus files loaded once at workflow start if needed
            plan=state.structured_plan or state.current_plan,
        )
        system_prompt = await prompt_builder.build(config)

        # Build messages with previous output context
        prev_output = results[-1].output if results else ""
        mission_msg = prompt_builder.build_mission_message(
            session_goal=state.session_goal,
            previous_output=prev_output,
        )
        messages = [HumanMessage(content=mission_msg)]

        # Execute single step
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
        except Exception as e:
            logger.error(f"[SequentialWorkflow] Step {step_index + 1} failed: {e}")
            blackboard.workflow_results = results + [
                WorkflowStepResult(
                    skill_id=getattr(skill, "id", None),
                    skill_name=skill_name,
                    output=str(e),
                    status="failed",
                )
            ]
            return StateUpdate(
                messages=[AIMessage(
                    content=f"Workflow failed at step {step_index + 1}: {e}",
                    metadata={"is_error": True, "error_type": "workflow_step_exception"}
                )],
                next_node=RoutingTarget.SUPERVISOR,
                blackboard=blackboard,
            )

        # Extract step output (defensive against empty messages)
        if engine_result.messages:
            last_msg = engine_result.messages[-1]
            step_output = get_message_text(last_msg) if isinstance(last_msg, AIMessage) else ""
        else:
            step_output = ""

        # Check for errors in output
        if "[ERROR:" in step_output or step_output.strip().startswith("Error:"):
            logger.error(f"[SequentialWorkflow] Step {step_index + 1} returned error")
            results.append(WorkflowStepResult(
                skill_id=getattr(skill, "id", None),
                skill_name=skill_name,
                output=step_output,
                status="failed",
            ))
            blackboard.workflow_results = results
            return StateUpdate(
                messages=[AIMessage(
                    content=f"Workflow failed at step {step_index + 1}/{len(plan)}: {skill_name}\n\n{step_output}",
                    metadata={"is_error": True, "error_type": "workflow_step_failed"}
                )],
                next_node=RoutingTarget.SUPERVISOR,
                blackboard=blackboard,
            )

        # Record success
        results.append(WorkflowStepResult(
            skill_id=getattr(skill, "id", None),
            skill_name=skill_name,
            output=step_output,
            status="success",
        ))

        blackboard.workflow_results = results
        blackboard.workflow_step_index = step_index + 1

        if is_last:
            logger.info("[SequentialWorkflow] Final step complete. Routing to FINISH.")
            return StateUpdate(
                messages=[AIMessage(content=f"Completed {len(plan)} step(s).")],
                next_node=RoutingTarget.FINISH,
                blackboard=blackboard,
            )

        # Route back to self for next step
        return StateUpdate(
            messages=[AIMessage(content=f"Step {step_index + 1} complete.")],
            next_node=RoutingTarget.SEQUENTIAL_WORKFLOW,
            blackboard=blackboard,
        )

    async def get_tools(self, state: AgentState) -> list[Any]:
        return await tool_manager.get_node_tools("worker", state)


# Singleton
sequential_workflow_node = SequentialWorkflowNode()
