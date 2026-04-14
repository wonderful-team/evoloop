"""
Routers - Functional Architecture (v3.0)

Simplified routing logic that supports the flattened graph topology.
"""
import ast
import copy
import logging
import operator
from collections.abc import Callable
from enum import Enum

from langgraph.types import Send

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.schema import EdgeCondition
from app.core.engine.state import AgentRuntimeConfig as AgentConfig
from app.core.engine.state import AgentState, ExecutionTicket

logger = logging.getLogger(__name__)


class RoutingTarget(str, Enum):
    """Supported routing targets for the agent system."""
    OPERATOR = "operator"
    DEEP_RESEARCHER = "deep_researcher"
    DOCUMENTER = "documenter"
    CHAT = "chat"
    FINISH = "finish"
    WORKER = "worker"
    FLASH_BRAIN = "flash_brain"
    SUPERVISOR = "supervisor"
    AGGREGATOR = "aggregator"
    SPAWN_SUBTASKS = "spawn_subtasks"


def route_supervisor(state: AgentState) -> str | list[Send]:
    """
    Decides the next node after Supervisor.
    """
    next_node = state.next_node
    blackboard = copy.deepcopy(state.blackboard) if state.blackboard else None
    if not blackboard:
        from app.core.engine.state.blackboard import BlackboardState
        blackboard = BlackboardState()

    # --- Phase 5: Resource Constraints Enforcement ---
    iteration_count = (state.iteration_count or 0)
    if iteration_count >= settings.SUPERVISOR_AGENT_MAX_STEPS:
        logger.warning(f"[Router] Hard limit reached ({iteration_count}/{settings.SUPERVISOR_AGENT_MAX_STEPS}). Forcing termination.")
        return RoutingTarget.FINISH

    # --- 🏅 Phase 4: Dynamic Subtask Spawning (Blackboard Driven) ---
    spawn_plan = blackboard.spawn_plan
    if spawn_plan and spawn_plan.subtasks:
        subtasks = spawn_plan.subtasks
        project_id = (state.project_id or DEFAULT_PROJECT_ID)
        parent_thread_id = (state.thread_id or "unknown")

        logger.info(f"[Router] Spawning {len(subtasks)} parallel subtasks")

        sends = []
        for i, subtask in enumerate(subtasks):
            subtask_id = subtask.id or f"subtask_{i}"
            # [CRITICAL Phase 5] Scoped Identity for concurrency safety
            scoped_thread_id = f"{parent_thread_id}:sub:{subtask_id}"

            skill_hint = subtask.skill_hint or getattr(spawn_plan, "suggested_skill", None)
            # Refined professional instructions for subtasks
            system_instructions = "Analyze the mission goal and execute the necessary tools effectively."
            if skill_hint:
                system_instructions += f" Use learned skill: {skill_hint}."

            # Get tools from subtask, but ensure it's not empty
            subtask_tools = subtask.tools or []
            # If no tools specified, allow all worker tools by not setting the field
            # (ToolManager will use full tool set when dynamic_tools is falsy)
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

            # Build rich context for subtask execution
            # Include description as acceptance criteria and context as parameters
            subtask_acceptance_criteria = []
            if subtask.description:
                subtask_acceptance_criteria.append(subtask.description)
            if subtask.title and subtask.title != subtask.intent:
                subtask_acceptance_criteria.append(f"Task: {subtask.title}")

            subtask_parameters = subtask.context or {}
            if subtask.dependencies:
                subtask_parameters["dependencies"] = subtask.dependencies

            # Inherit historical context from parent task's execution_ticket (if available)
            parent_ticket = state.execution_ticket

            ticket = ExecutionTicket(
                ticket_type="subtask",
                topic=subtask["intent"],
                parent_task_id=parent_thread_id,
                subtask_id=subtask_id,
                agent_config=agent_config,
                acceptance_criteria=subtask_acceptance_criteria if subtask_acceptance_criteria else None,
                parameters=subtask_parameters if subtask_parameters else None,
                # Inherit historical context from parent task for continuity
                historical_context=parent_ticket.historical_context if parent_ticket else None,
                referenced_tech=parent_ticket.referenced_tech if parent_ticket else None,
                # [NEW] Macro context for subtask alignment
                macro_goal=parent_ticket.topic if parent_ticket else None,
                # Note: MCP servers are NOT inherited by subtasks
                # Each subtask must explicitly request MCP servers via use_mcp_server
            )

            sends.append(Send(RoutingTarget.WORKER, {
                "project_id": project_id,
                "thread_id": scoped_thread_id, # Target isolation
                "execution_ticket": ticket,
                "blackboard": copy.deepcopy(blackboard), # Deep copy to prevent subtask mutation affecting parent
                "is_subtask": True,
                # [CRITICAL] Start with empty messages to prevent inheriting parent history
                # Worker will set the mission message via build_mission_message()
                "messages": [],
            }))

        # Consume the spawn_plan to prevent re-triggering on next router pass
        blackboard["spawn_plan"] = None

        return sends

    # --- Phase 5: Routing Topology Whitelist ---
    # These nodes can be reached directly from Supervisor without an execution ticket wrapper
    terminal_nodes = (
        RoutingTarget.CHAT,
        RoutingTarget.FINISH,
        RoutingTarget.SUPERVISOR,
        RoutingTarget.AGGREGATOR,
        RoutingTarget.SPAWN_SUBTASKS
    )
    if next_node in terminal_nodes:
        return next_node

    if next_node:
        logger.info(f"[Router] Remapping intelligent target '{next_node}' -> 'worker'")

        # Extract execution_ticket from blackboard (set by SignalDispatcher)
        # and place it at state root for WorkerNode to access
        execution_ticket = blackboard.ticket
        if execution_ticket:
            # Use Send to pass execution_ticket to worker
            return Send(RoutingTarget.WORKER, {
                "project_id": (state.project_id or DEFAULT_PROJECT_ID),
                "execution_ticket": execution_ticket,
            })

        # CRITICAL: No execution ticket found - this indicates a Supervisor routing bug
        logger.error(f"[Router] CRITICAL: No execution ticket in blackboard for target '{next_node}'. "
                     f"Supervisor must always create a ticket via route_to when routing to worker-like nodes.")
        raise ValueError(
            f"Supervisor routing error: No execution ticket found for target '{next_node}'. "
            "Supervisor must call route_to() with a valid execution_ticket before routing to Worker."
        )

    return "finish"


def _safe_eval_expr(expr: str, context: dict) -> bool:
    """
    Safely evaluate a boolean expression using AST.
    Only allows a restricted set of operations to prevent code injection.
    """
    # Block dangerous patterns
    if not expr or "import" in expr or "__" in expr:
        return False

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False

    # Allowed node types for safe evaluation
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.Num,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Is,
        ast.IsNot,
        ast.In,
        ast.NotIn,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.Call,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.Str,
        ast.NameConstant,
    )

    # Check all nodes are allowed
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            logger.warning(f"[SafeEval] Disallowed node type: {type(node).__name__}")
            return False

    # Execute safely
    def _eval_node(node):
        if isinstance(node, ast.BoolOp):
            values = [_eval_node(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            elif isinstance(node.op, ast.Or):
                return any(values)
        elif isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            if isinstance(node.op, ast.Not):
                return not operand
        elif isinstance(node, ast.Compare):
            left = _eval_node(node.left)
            ops = {
                ast.Eq: operator.eq,
                ast.NotEq: operator.ne,
                ast.Lt: operator.lt,
                ast.LtE: operator.le,
                ast.Gt: operator.gt,
                ast.GtE: operator.ge,
                ast.Is: operator.is_,
                ast.IsNot: operator.is_not,
            }
            # Block In/NotIn to prevent __contains__ exploitation
            result = True
            for op_node, comparator in zip(node.ops, node.comparators, strict=False):
                if type(op_node) in (ast.In, ast.NotIn):
                    return False
                right = _eval_node(comparator)
                op_func = ops.get(type(op_node))
                if op_func is None:
                    return False
                result = result and op_func(left, right)
                left = right
            return result
        elif isinstance(node, ast.BinOp):
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Mod: operator.mod,
                ast.Pow: operator.pow,
            }
            op_func = ops.get(type(node.op))
            if op_func is None:
                return False
            return op_func(left, right)
        elif isinstance(node, ast.Call):
            # Only allow specific safe functions
            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                func_name = f"{node.func.value.id}.{node.func.attr}"

            allowed_funcs = {"len", "int", "str", "bool", "blackboard.get"}  # state.get removed - router decisions should only use blackboard
            if func_name not in allowed_funcs:
                return False

            args = [_eval_node(arg) for arg in node.args]
            kwargs = {kw.arg: _eval_node(kw.value) for kw in node.keywords}

            # Use direct function calls instead of eval
            func_map = {
                "len": len,
                "int": int,
                "str": str,
                "bool": bool,
            }
            if func_name in func_map:
                return func_map[func_name](*args, **kwargs)
            elif func_name == "blackboard.get":
                return context.get("blackboard", {}).get(*args, **kwargs)
            # state.get removed - router decisions should only use blackboard, not full state
            return False
        elif isinstance(node, ast.Name):
            # Direct value lookup, no eval
            if node.id == "True":
                return True
            if node.id == "False":
                return False
            if node.id == "None":
                return None
            if node.id in context:
                return context[node.id]
            return False
        # Removed: ast.Attribute, ast.Subscript - prevent sandbox escape
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.NameConstant):
            return node.value
        elif isinstance(node, ast.List):
            return [_eval_node(elt) for elt in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(_eval_node(elt) for elt in node.elts)
        elif isinstance(node, ast.Dict):
            return {_eval_node(k): _eval_node(v) for k, v in zip(node.keys, node.values, strict=False)}
        return False

    return _eval_node(tree.body)


def make_expression_router(conditions: list[EdgeCondition], default: str) -> Callable[[AgentState], str]:
    def expression_router(state: AgentState) -> str:
        # Prepare evaluation context (Phase 4: Blackboard Only)
        blackboard = state.blackboard or {}
        eval_context = {
            "state": state,
            "blackboard": blackboard,
            "len": len,
            "int": int,
            "str": str,
            "bool": bool,
        }

        for case in conditions:
            expr = case.expr
            to_node = case.to

            try:
                result = _safe_eval_expr(expr, eval_context)
                if result:
                    logger.info(f"Router Expression '{expr}' matched. Routing to {to_node}")
                    return to_node
            except Exception as e:
                logger.error(f"Error evaluating expression '{expr}': {e}")

        logger.info(f"No expressions matched. Routing to default: {default}")
        return default

    return expression_router
