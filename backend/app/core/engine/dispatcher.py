import copy
import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.routers import RoutingTarget
from app.core.engine.signals import RouteToSignal, SpawnSubtasksSignal, TerminateSignal

logger = logging.getLogger(__name__)


class SignalDispatcher:
    """
    Centralized dispatcher for AgentSignals (Phase 2).
    Translates architectural signals into Graph state transitions.
    """

    @staticmethod
    async def dispatch(state: dict, signal: Any, config: RunnableConfig) -> dict:
        """
        Dispatches the signal and returns the updated state for the next node.
        """
        if isinstance(signal, RouteToSignal):
            return await SignalDispatcher._handle_route_to(state, signal, config)
        elif isinstance(signal, SpawnSubtasksSignal):
            return await SignalDispatcher._handle_spawn_subtasks(state, signal, config)
        elif isinstance(signal, TerminateSignal):
            return await SignalDispatcher._handle_terminate(state, signal, config)
        
        logger.warning(f"[Dispatcher] Unknown signal type: {type(signal)}")
        return {"next_node": RoutingTarget.SUPERVISOR}

    @staticmethod
    async def _handle_route_to(state: dict, signal: RouteToSignal, config: RunnableConfig) -> dict:
        target = signal.target
        reason = signal.reason
        routing_context = signal.context
        authorized_tools = signal.authorized_tools

        logger.info(f"[Dispatcher] ✅ Routing to: {target} | Reason: {reason}")

        # 1. Update Blackboard (Phase 1 Pattern)
        blackboard = copy.deepcopy(state.get("blackboard", {}))
        blackboard["route_reason"] = reason
        
        # 2. Construct Execution Ticket
        inferred_namespace = routing_context.get("namespace_context")
        
        agent_config = routing_context.get("agent_config") or {}
        if "namespace_context" not in agent_config:
            agent_config["namespace_context"] = inferred_namespace
        
        if not agent_config.get("role_name"):
            agent_config["role_name"] = str(target).replace("_", " ").title()
        
        if authorized_tools is not None:
            agent_config["tools"] = authorized_tools

        reserved_keys = {
            "ticket_type", "priority", "focus_paths", "topic", "query", 
            "acceptance_criteria", "constraints", "agent_config", "namespace_context"
        }
        parameters = {k: v for k, v in routing_context.items() if k not in reserved_keys}

        execution_ticket = {
            "ticket_type": routing_context.get("ticket_type", "task"),
            "priority": routing_context.get("priority", "normal"),
            "focus_paths": routing_context.get("focus_paths", []),
            "topic": routing_context.get("topic") or routing_context.get("query") or reason,
            "acceptance_criteria": routing_context.get("acceptance_criteria", []),
            "constraints": routing_context.get("constraints", []),
            "agent_config": agent_config,
            "namespace_context": inferred_namespace,
            "skill_id": signal.skill_id,
            "skill_ids": routing_context.get("skill_ids"),  # 新增：多技能工作流
            "workflow_mode": routing_context.get("workflow_mode", "single"),  # 新增：工作流模式
            "macro_goal": routing_context.get("macro_goal"),  # 新增：背景同步
            "parameters": parameters,
        }
        blackboard["ticket"] = execution_ticket

        # 3. Handle Blackboard/Loop Detection
        visited_nodes = blackboard.get("visited_nodes", [])
        if target not in visited_nodes:
            visited_nodes = visited_nodes + [target]
        blackboard["visited_nodes"] = visited_nodes

        return {
            "next_node": target,
            "blackboard": blackboard,
            "execution_ticket": execution_ticket
        }

    @staticmethod
    async def _handle_spawn_subtasks(state: dict, signal: SpawnSubtasksSignal, config: RunnableConfig) -> dict:
        spawn_plan = signal.plan
        logger.info(f"[Dispatcher] 🚀 Spawning {len(spawn_plan.get('subtasks', []))} parallel subtasks")

        blackboard = copy.deepcopy(state.get("blackboard", {}))
        blackboard["spawn_plan"] = spawn_plan

        if spawn_plan.get("_requires_aggregation"):
            blackboard["pending_aggregation"] = {
                "strategy": spawn_plan.get("aggregation_strategy", "merge"),
                "expected_count": len(spawn_plan.get("subtasks", [])),
                "parent_task": spawn_plan.get("parent_task", "")
            }

        return {
            "next_node": RoutingTarget.SPAWN_SUBTASKS,
            "blackboard": blackboard
        }

    @staticmethod
    async def _handle_terminate(state: dict, signal: TerminateSignal, config: RunnableConfig) -> dict:
        logger.info(f"[Dispatcher] 🏁 Natural Termination Signal received. Outcome: {signal.outcome}")
        
        blackboard = copy.deepcopy(state.get("blackboard", {}))
        metadata = copy.deepcopy(blackboard.get("metadata", {}))
        metadata["shadow_audit"] = True
        metadata["termination_outcome"] = signal.outcome
        blackboard["metadata"] = metadata

        return {
            "next_node": RoutingTarget.FINISH,
            "blackboard": blackboard
        }
