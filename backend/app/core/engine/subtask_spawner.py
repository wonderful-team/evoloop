"""
Subtask spawning builder for parallel agent execution.

Builds Send objects for LangGraph conditional edges to create
parallel Worker subgraphs from a Supervisor spawn plan.
"""

import logging

from langgraph.types import Send

from app.constants import DEFAULT_PROJECT_ID
from app.core.engine.state import AgentRuntimeConfig as AgentConfig
from app.core.engine.state import AgentState, ExecutionTicket
from app.core.engine.state.blackboard import BlackboardState

logger = logging.getLogger(__name__)


def build_subtask_sends(state: AgentState, blackboard: BlackboardState) -> list[Send]:
    """
    Build a list of Send objects for parallel subtask execution.

    This is the *only* place in the router layer that returns ``list[Send]``.
    LangGraph conditional edges support ``list[Send]`` as a special return
    value that creates parallel subgraphs.  When the subgraphs finish, their
    state updates are merged back and execution resumes at the source node
    (Supervisor).

    IMPORTANT: This function mutates ``blackboard.spawn_plan = None`` so the
    spawn is not re-triggered on the next router pass.
    """
    spawn_plan = blackboard.spawn_plan
    subtasks = spawn_plan.subtasks
    project_id = state.project_id or DEFAULT_PROJECT_ID
    parent_thread_id = state.thread_id or "unknown"

    logger.info(f"[Router] Spawning {len(subtasks)} parallel subtasks")

    sends = []
    for i, subtask in enumerate(subtasks):
        subtask_id = subtask.id or f"subtask_{i}"
        scoped_thread_id = f"{parent_thread_id}:sub:{subtask_id}"

        skill_hint = subtask.skill_hint or spawn_plan.suggested_skill
        system_instructions = "Analyze the mission goal and execute the necessary tools effectively."
        if skill_hint:
            system_instructions += f" Use learned skill: {skill_hint}."

        subtask_tools = subtask.tools or []
        agent_config = AgentConfig(
            role_name=f"Field Specialist {subtask_id}",
            system_instructions=system_instructions,
            is_subtask=True,
            subtask_context=subtask.context or {},
            skill_hint=skill_hint,
            tools=subtask_tools if subtask_tools else None,
        )
        if subtask_tools:
            logger.info(f"[Router] Subtask {subtask_id} assigned tools: {subtask_tools}")
        else:
            logger.info(f"[Router] Subtask {subtask_id} using full worker tool set")

        subtask_acceptance_criteria = []
        if subtask.description:
            subtask_acceptance_criteria.append(subtask.description)
        if subtask.title and subtask.title != subtask.intent:
            subtask_acceptance_criteria.append(f"Task: {subtask.title}")

        subtask_parameters = subtask.context or {}
        if subtask.dependencies:
            subtask_parameters["dependencies"] = subtask.dependencies

        parent_ticket = state.blackboard.ticket if state.blackboard else None

        ticket = ExecutionTicket(
            ticket_type="subtask",
            topic=subtask["intent"],
            parent_task_id=parent_thread_id,
            subtask_id=subtask_id,
            agent_config=agent_config,
            acceptance_criteria=subtask_acceptance_criteria if subtask_acceptance_criteria else None,
            parameters=subtask_parameters if subtask_parameters else None,
            historical_context=parent_ticket.historical_context if parent_ticket else None,
            referenced_tech=parent_ticket.referenced_tech if parent_ticket else None,
            macro_goal=parent_ticket.topic if parent_ticket else None,
        )

        subtask_blackboard = blackboard.model_copy(deep=True)
        subtask_blackboard.ticket = ticket
        sends.append(Send("worker", {
            "project_id": project_id,
            "thread_id": scoped_thread_id,
            "blackboard": subtask_blackboard,
            "is_subtask": True,
            "messages": [],
        }))

    # Consume the spawn_plan to prevent re-triggering on next router pass
    blackboard.spawn_plan = None
    return sends
