"""Tests for HITL shared prompt helpers (app/core/hitl/prompts.py).

Covers:
1. ``format_risk_header``: standard levels map to emoji + i18n label; unknown
   business levels pass through verbatim.
2. ``build_approval_context``: unified section ordering + selective inclusion.
3. ``resolve_tool_context``: extracts ctx fields, raises when thread_id missing.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.hitl.prompts import (
    build_approval_context,
    format_risk_header,
    resolve_tool_context,
)


class TestFormatRiskHeader:
    @pytest.mark.parametrize(
        ("level", "emoji"),
        [("low", "🟢"), ("medium", "🟡"), ("high", "🟠"), ("critical", "🔴")],
    )
    def test_standard_levels(self, level, emoji):
        header = format_risk_header(level)
        assert header.startswith(emoji)
        assert "风险等级" in header

    def test_unknown_business_level_passthrough(self):
        # 业务等级（如 MCP [risk:T1]）不透传标准文案，原样展示
        header = format_risk_header("T1")
        assert header.startswith("⚪")
        assert "T1" in header


class TestBuildApprovalContext:
    def test_action_only(self):
        ctx = build_approval_context(action_description="删除文件")
        assert "删除文件" in ctx
        # 未提供的段落不应出现
        assert "详情" not in ctx
        assert "资源" not in ctx

    def test_full_sections_in_order(self):
        ctx = build_approval_context(
            action_description="删除文件",
            risk_level="high",
            details="删除 /tmp/x",
            consequences="不可恢复",
            resource_path="/tmp/x",
            policy_description="敏感文件策略",
            extra_lines=["自定义说明"],
        )
        # 顺序：风险 → 操作 → 资源 → 详情 → 后果 → 策略 → 自定义
        positions = [
            ctx.index("风险等级"),
            ctx.index("删除文件"),  # 操作
            ctx.index("资源"),
            ctx.index("详情"),
            ctx.index("潜在后果"),
            ctx.index("敏感文件策略"),
            ctx.index("自定义说明"),
        ]
        assert positions == sorted(positions), positions

    def test_optional_skipped(self):
        ctx = build_approval_context(action_description="只读操作", risk_level=None)
        assert "风险等级" not in ctx


class TestResolveToolContext:
    def test_returns_fields(self):
        ctx = MagicMock()
        ctx.thread_id = "t-1"
        ctx.project_id = 120
        ctx.command_id = "cmd-1"
        ctx.current_tool_call_id = "call-1"
        ctx.last_ai_message_id = "msg-1"

        with patch("app.core.context.manager.ContextManager.current", return_value=ctx):
            fields = resolve_tool_context()

        assert fields == {
            "thread_id": "t-1",
            "project_id": 120,
            "command_id": "cmd-1",
            "tool_call_id": "call-1",
            "parent_id": "msg-1",
        }

    def test_missing_thread_id_raises(self):
        ctx = MagicMock()
        ctx.thread_id = None

        with (
            patch("app.core.context.manager.ContextManager.current", return_value=ctx),
            pytest.raises(ValueError),
        ):
            resolve_tool_context()
