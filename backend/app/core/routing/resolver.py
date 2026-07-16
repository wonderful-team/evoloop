"""Deterministic cross-intent parameter resolver (方案甲).

When one instruction carries dependent intents ("查铰链价格，然后降价10%"),
the decomposition layer emits param expressions referencing earlier intents'
extracted data: {"new_value": "{{1.price}} * 0.9"}. This module evaluates
such expressions to ABSOLUTE values before the dependent macro starts — the
macro layer's absolute-value gate is never bypassed, and no LLM touches the
arithmetic.

Safety: refs are substituted as numeric literals, then the expression is
evaluated over a whitelist AST (arithmetic + round/min/max/abs/float/int).
Anything else raises ResolveError -> the caller hands that intent to the
Agent (方案乙 fallback).
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any


class ResolveError(ValueError):
    """Unresolvable expression: missing ref, non-numeric value, illegal syntax."""


_REF_RE = re.compile(r"\{\{\s*(\d+)\.([a-zA-Z0-9_\-\.]+)\s*\}\}")

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "round": round,
    "min": min,
    "max": max,
    "abs": abs,
    "float": float,
    "int": int,
}


def _to_number(raw: Any, ref: str) -> float:
    """Coerce an extracted value ("￥99", "100", 3) to float."""
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        cleaned = re.sub(r"[^\d.\-]", "", raw)
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                pass
    raise ResolveError(f"引用 {ref} 的值不是数值: {raw!r}")


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ResolveError(f"非法常量: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ResolveError(f"不支持的运算符: {type(node.op).__name__}")
        right = _eval_node(node.right)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ResolveError("除数为零")
        return op(_eval_node(node.left), right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ResolveError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ResolveError("只允许 round/min/max/abs/float/int 函数")
        if node.keywords:
            raise ResolveError("不支持关键字参数")
        args = [_eval_node(a) for a in node.args]
        if node.func.id in ("round", "int"):
            # round(x, ndigits) and int(x) require integer args where present
            args = [int(a) if i else a for i, a in enumerate(args)]
        return float(_FUNCS[node.func.id](*args))
    raise ResolveError(f"非法表达式节点: {type(node).__name__}")


def resolve_expression(expr: str, prior_results: dict[int, dict[str, Any]]) -> float:
    """Evaluate one param expression like "{{1.price}} * 0.9".

    `prior_results` maps 1-based intent index -> that intent's extracted_data.
    """

    def _sub(match: re.Match) -> str:
        idx, key = int(match.group(1)), match.group(2)
        data = prior_results.get(idx)
        if data is None:
            raise ResolveError(f"第 {idx} 个意图没有产出数据")
        value: Any = data
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                raise ResolveError(f"第 {idx} 个意图的产出中没有 '{key}'")
        return repr(_to_number(value, f"{idx}.{key}"))

    substituted = _REF_RE.sub(_sub, expr)
    if "{{" in substituted:
        raise ResolveError(f"存在无法识别的引用: {expr}")
    try:
        tree = ast.parse(substituted, mode="eval")
    except SyntaxError as exc:
        raise ResolveError(f"表达式语法非法: {expr}") from exc
    return _eval_node(tree)


def resolve_params(
    param_exprs: dict[str, str],
    prior_results: dict[int, dict[str, Any]],
) -> dict[str, float]:
    """Resolve every param expression to an absolute numeric value."""
    return {
        name: resolve_expression(expr, prior_results)
        for name, expr in param_exprs.items()
    }
