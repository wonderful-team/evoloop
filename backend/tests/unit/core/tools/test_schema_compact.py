"""compact_schema_for_llm 契约测试（工具面递归瘦身，2026-09-18）。

锁定语义：
1. 全层级 title 移除；值为 null 的 default 移除；
2. {"anyOf": [X, {"type": "null"}]} 塌缩为 X + type: [T, "null"]（nullable 保留）；
3. 保守边界：$ref / 多分支 anyOf / 非 type 限定组合不动；非空 default 保留。
"""

from __future__ import annotations

from app.core.tools.schema_utils import compact_schema_for_llm


def test_strips_nested_titles_and_null_defaults():
    schema = {
        "title": "Root",
        "type": "object",
        "properties": {
            "command": {"title": "Command", "type": "string"},
            "timeout": {
                "title": "Timeout",
                "type": "integer",
                "default": None,
            },
        },
        "required": ["command"],
    }
    out = compact_schema_for_llm(schema)
    assert "title" not in out
    props = out["properties"]
    assert "title" not in props["command"]
    assert "title" not in props["timeout"]
    assert "default" not in props["timeout"]
    assert props["timeout"]["type"] == "integer"
    assert out["required"] == ["command"]


def test_collapses_nullable_anyof():
    schema = {
        "type": "object",
        "properties": {
            "scope": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
                "title": "Scope",
            }
        },
    }
    out = compact_schema_for_llm(schema)
    prop = out["properties"]["scope"]
    # nullable 语义保留（模型显式传 null 不违约），anyOf 包装消除
    assert prop["type"] == ["string", "null"]
    assert "anyOf" not in prop
    assert "title" not in prop
    assert "default" not in prop


def test_keeps_non_null_default_and_multibranche_anyof():
    schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 20},
            "complex": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "object", "properties": {"a": {"type": "string"}}},
                ]
            },
            "refed": {"anyOf": [{"$ref": "#/$defs/X"}, {"type": "null"}]},
        },
    }
    out = compact_schema_for_llm(schema)
    props = out["properties"]
    assert props["limit"]["default"] == 20  # 非空 default 保留
    assert "anyOf" in props["complex"]  # 多分支不动
    assert "anyOf" in props["refed"]  # 含 $ref 不动


def test_noop_on_scalar_and_preserves_required_semantics():
    schema = {"type": "object", "properties": {}, "required": ["a"]}
    assert compact_schema_for_llm(schema) == schema
    assert compact_schema_for_llm({"type": "string"}) == {"type": "string"}


def test_param_named_title_survives_compaction():
    """回归锁：properties 里名为 title 的参数不是噪音键，整条定义必须保留。

    （曾有递归清洗把 `title` 参数当作 Pydantic 元数据键误删，导致
    tasks/plan 的 create 无法向模型暴露 title 入参。）"""
    schema = {
        "type": "object",
        "title": "TasksAutoSchema",
        "properties": {
            "action": {"type": "string", "title": "Action", "enum": ["list", "create"]},
            "title": {"type": "string", "title": "Title", "description": "creation field"},
            "nested": {
                "type": "object",
                "title": "Nested",
                "properties": {"title": {"type": "string", "title": "Title"}},
            },
        },
        "required": ["action"],
    }
    out = compact_schema_for_llm(schema)
    assert "title" in out["properties"]                      # 参数定义保留
    assert out["properties"]["title"]["description"] == "creation field"
    assert "title" not in out["properties"]["title"]         # 参数自身的元数据 title 仍被清
    assert "title" not in out                                # 根节点元数据仍被清
    assert "title" in out["properties"]["nested"]["properties"]
    assert "title" not in out["properties"]["nested"]
    assert "title" not in out["properties"]["action"]
