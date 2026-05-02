"""
Safe expression evaluator for conditional routing.

Uses AST-based evaluation to prevent code injection while supporting
basic boolean expressions, comparisons, and a limited set of functions.
"""

import ast
import logging
import operator
from collections.abc import Callable

from app.core.engine.schemas import EdgeCondition
from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


def _safe_eval_expr(expr: str, context: dict) -> bool:
    """
    Safely evaluate a boolean expression using AST.
    Only allows a restricted set of operations to prevent code injection.
    """
    # Block dangerous patterns
    if not expr or "import" in expr or "__" in expr:
        return False

    # Syntax errors in expressions should be caught early (usually during graph build)
    # but if they happen at runtime, they are fatal bugs.
    tree = ast.parse(expr, mode="eval")

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
        blackboard = state.blackboard
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

            # Evaluation errors (e.g. missing blackboard keys, type mismatch) 
            # should be raised to prevent incorrect routing decisions.
            result = _safe_eval_expr(expr, eval_context)
            if result:
                logger.info(f"Router Expression '{expr}' matched. Routing to {to_node}")
                return to_node

        logger.info(f"No expressions matched. Routing to default: {default}")
        return default

    return expression_router
