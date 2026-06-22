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

logger = logging.getLogger(__name__)


def build_subtask_sends(state: AgentState) -> list[Send]:
    """
    Build a list of Send objects for parallel subtask execution.

    This is the *only* place in the router layer that returns ``list[Send]``.
    LangGraph conditional edges support ``list[Send]`` as a special return
    value that creates parallel subgraphs.  When the subgraphs finish, their
    state updates are merged back and execution resumes at the source node
    (Supervisor).

    IMPORTANT: This function mutates ``state.spawn_plan = None`` so the
    spawn is not re-triggered on the next router pass.
    """
    spawn_plan = state.spawn_plan
    if spawn_plan is None:
        return []
    subtasks = spawn_plan.subtasks
    project_id = state.project_id if state.project_id is not None else DEFAULT_PROJECT_ID
    parent_thread_id = state.thread_id or "unknown"

    logger.info(f"[Router] Spawning {len(subtasks)} parallel subtasks")

    sends = []
    for i, subtask in enumerate(subtasks):
        subtask_id = subtask.id or f"subtask_{i}"
        scoped_thread_id = f"{parent_thread_id}:sub:{subtask_id}"

        skill_hint = subtask.skill_hint or getattr(spawn_plan, "suggested_skill", None)
        # P2 Improvement: Inject specific subtask description into system instructions
        system_instructions = f"Mission: {subtask.intent or 'Execute task'}.\n"
        if subtask.description:
            system_instructions += f"Details: {subtask.description}\n"
        system_instructions += "Analyze the goal and execute the necessary tools effectively."
        if skill_hint:
            system_instructions += f" Use learned skill: {skill_hint}."

        subtask_tools = subtask.tools or []
        agent_config = AgentConfig(
            role_name=f"Field Specialist {subtask_id}",
            system_instructions=system_instructions,
            is_subtask=True,
            subtask_context=subtask.context,
            skill_hint=skill_hint,
            tools=subtask_tools,
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

        parent_ticket = state.ticket

        ticket = ExecutionTicket(
            ticket_type="subtask",
            topic=subtask.intent,
            parent_task_id=parent_thread_id,
            subtask_id=subtask_id,
            agent_config=agent_config,
            acceptance_criteria=subtask_acceptance_criteria if subtask_acceptance_criteria else None,
            parameters=subtask_parameters if subtask_parameters else None,  # type: ignore[arg-type]
            historical_context=parent_ticket.historical_context if parent_ticket else None,
            referenced_tech=parent_ticket.referenced_tech if parent_ticket else None,
            macro_goal=parent_ticket.topic if parent_ticket else None,
        )

        sends.append(Send("worker", {
            "project_id": project_id,
            "thread_id": scoped_thread_id,
            "ticket": ticket,
            "is_subtask": True,
            "messages": [],
        }))

    # Consume the spawn_plan to prevent re-triggering on next router pass
    state.spawn_plan = None
    return sends
