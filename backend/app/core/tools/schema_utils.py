"""JSON Schema 工具定义清洗工具。

MCP 工具自带完整的 JSON Schema（含嵌套 properties/items/enum/oneOf/判别字段）。
模型侧（OpenAI ``parameters`` / Anthropic ``input_schema``）需要完整结构才能
正确构造参数；此前仅用 Pydantic ``model_json_schema()`` 拍平会导致嵌套信息丢失。
这里提供：
- ``resolve_refs``: 把 ``$ref`` 从 ``$defs``/``definitions`` 内联展开
- ``clean_tool_schema``: 通用的轻量清洗（去 ``$schema/$id/title/additionalProperties``）
- ``clean_tool_schema_for_anthropic``: 在通用清洗基础上，去除 Anthropic 不接受的
  ``$defs``（已内联）与 ``default``，并限定根节点为 object
"""

from __future__ import annotations

import copy
from typing import Any


def resolve_refs(
    schema: Any,
    defs: dict[str, Any] | None = None,
    _seen: set[int] | None = None,
) -> Any:
    """递归展开 JSON Schema 中的 ``$ref``（基于 ``$defs`` / ``definitions``）。

    Anthropic 的 ``input_schema`` 不支持 ``$ref``，必须先内联成完整结构。
    """
    if _seen is None:
        _seen = set()

    if isinstance(schema, list):
        return [resolve_refs(item, defs, _seen) for item in schema]

    if not isinstance(schema, dict):
        return schema

    # 收集当前层的 $defs / definitions 供内部 $ref 使用
    local_defs = dict(defs or {})
    for key in ("$defs", "definitions"):
        inner = schema.get(key)
        if isinstance(inner, dict):
            local_defs.update(inner)

    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.split("/")[-1]
        target = local_defs.get(name) or (defs or {}).get(name)
        marker = id(target)
        if target is None:
            resolved: Any = {}
        elif marker in _seen:
            # 循环引用：无法内联，退化为空对象，避免无限递归
            resolved = {"type": "object"}
        else:
            _seen.add(marker)
            resolved = resolve_refs(copy.deepcopy(target), local_defs, _seen)
            _seen.discard(marker)
        # $ref 节点的兄弟字段（如 description）应保留
        siblings = {k: v for k, v in schema.items() if k != "$ref"}
        if siblings:
            merged = dict(resolved or {})
            for k, v in siblings.items():
                if k not in ("$defs", "definitions"):
                    merged.setdefault(k, resolve_refs(v, local_defs, _seen))
            return merged
        return resolved

    return {k: resolve_refs(v, local_defs, _seen) for k, v in schema.items()}


def clean_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """通用轻量清洗：去掉模型侧不需要/不接受的元数据键，返回可发送给模型的 schema。"""
    cleaned = copy.deepcopy(schema)
    cleaned.pop("$schema", None)
    cleaned.pop("$id", None)
    cleaned.pop("title", None)
    cleaned.pop("additionalProperties", None)
    return cleaned


def compact_schema_for_llm(schema: dict[str, Any]) -> dict[str, Any]:
    """面向 LLM 工具面的递归瘦身（OpenAI 兼容 function calling）。

    与 ``clean_tool_schema`` 的区别：clean 只清根层元数据；本函数递归处理全部
    层级，消除 Pydantic v2 ``model_json_schema()`` 生成的大量结构性噪音
    （实测 20 工具面约 18k token 中噪音占一半以上）：

    - schema 节点上的 ``title``：对模型无意义；
    - 值为 ``null`` 的 ``default``：可选性已由 ``required`` 表达；
    - ``{"anyOf": [X, {"type": "null"}]}`` 塌缩为 X + ``type: [T, "null"]``：
      保留 nullable 语义，消除 anyOf 包装的重复结构。

    保守边界：含 ``$ref`` / 多分支 anyOf / 非 type 限定的组合键原样保留，
    非空 ``default`` 保留（对模型有默认值提示作用）。
    ``properties``/``$defs`` 等**命名映射**里名为 title 的参数不是噪音，
    必须保留（曾有参数叫 title 的整条定义被当噪音误删的事故）。
    """
    return _compact_node(copy.deepcopy(schema), named_map=False)


_NAMED_MAP_KEYS = frozenset({"properties", "patternProperties", "$defs", "definitions", "dependencies"})


def _compact_node(node: Any, *, named_map: bool) -> Any:
    if isinstance(node, list):
        return [_compact_node(item, named_map=False) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if not named_map:
            if key == "title":
                continue
            if key == "default" and value is None:
                continue
            if key == "anyOf":
                collapsed = _collapse_nullable_anyof(value)
                if collapsed is not None:
                    merged = dict(collapsed)
                    # anyOf 节点自身的兄弟键保留（但 title / default:null 仍按
                    # 本函数语义剔除，不能因走塌缩分支而回流）
                    for sib_key, sib_val in node.items():
                        if sib_key == "anyOf" or sib_key in merged:
                            continue
                        if sib_key == "title" or (sib_key == "default" and sib_val is None):
                            continue
                        merged[sib_key] = _compact_node(
                            sib_val, named_map=sib_key in _NAMED_MAP_KEYS
                        )
                    out.update(merged)
                    continue
        out[key] = _compact_node(value, named_map=key in _NAMED_MAP_KEYS)
    return out


def _collapse_nullable_anyof(branches: Any) -> dict[str, Any] | None:
    """``[X, {"type": "null"}]`` → X 且 type 变为 ``[T, "null"]``；不匹配返回 None。"""
    if (
        not isinstance(branches, list)
        or len(branches) != 2
        or not all(isinstance(b, dict) for b in branches)
    ):
        return None
    null_branch = next((b for b in branches if b == {"type": "null"}), None)
    other = next((b for b in branches if b is not null_branch), None)
    if null_branch is None or other is None:
        return None
    if any(k in other for k in ("$ref", "anyOf", "oneOf", "allOf")):
        return None
    base_type = other.get("type")
    if not isinstance(base_type, str):
        return None
    merged = {
        k: _compact_node(v, named_map=k in _NAMED_MAP_KEYS) for k, v in other.items()
    }
    merged["type"] = [base_type, "null"]
    return merged


def clean_tool_schema_for_anthropic(schema: dict[str, Any]) -> dict[str, Any]:
    """清洗为 Anthropic ``input_schema`` 兼容的结构。

    - 先内联 ``$ref``（Anthropic 不支持）
    - 去掉 ``$defs``/``definitions``（已内联）
    - 去掉 ``$schema/$id/title/additionalProperties/default``（Anthropic 常拒绝）
    - 根节点必须是 object（若原始是 oneOf/anyOf 根，退化为宽松 object）
    """
    schema = resolve_refs(schema)
    cleaned = copy.deepcopy(schema)
    cleaned.pop("$schema", None)
    cleaned.pop("$id", None)
    cleaned.pop("title", None)
    cleaned.pop("additionalProperties", None)
    cleaned.pop("$defs", None)
    cleaned.pop("definitions", None)

    _strip_defaults(cleaned)

    if cleaned.get("type") != "object":
        return {"type": "object", "properties": cleaned.get("properties", {})}
    return cleaned


def _strip_defaults(node: Any) -> None:
    """递归移除 ``default`` 键（Anthropic 对部分位置的 default 会报错）。"""
    if isinstance(node, dict):
        node.pop("default", None)
        for value in node.values():
            _strip_defaults(value)
    elif isinstance(node, list):
        for item in node:
            _strip_defaults(item)
