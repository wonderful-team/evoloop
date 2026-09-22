"""Tests for HITL authorization resolve: APPROVED grants+executes, REJECTED does not.

Critical security semantics: when a user rejects access to a path outside the
workspace, the tool must NOT be re-executed and permission must NOT be granted.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.hitl.orchestrator import HITLOrchestrator


def _pending_tool(**overrides):
    base = {
        "id": "call-1",
        "name": "list_dir",
        "args": {"path": "/tmp/outside"},
        "authorization": {"resource_path": "/tmp/outside", "action": "read"},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_rejected_does_not_grant_nor_execute():
    """REJECTED → no grant_permission, no re-execution, returns 'REJECTED'."""
    with patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls:
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        result = await HITLOrchestrator.resolve_approved_tool_result(
            _pending_tool(),
            {"metadata": {"project_id": 120}},
            "REJECTED",
            state=None,
        )
    assert result.startswith("[AUTHORIZATION REJECTED]")
    assert "未执行" in result
    assert "/tmp/outside" in result
    mock_auth.grant_permission.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_grants_and_executes():
    """APPROVED → grant_permission called, tool re-executed."""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="✅ listed /tmp/outside")

        result = await HITLOrchestrator.resolve_approved_tool_result(
            _pending_tool(),
            {"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
        )
    assert "✅ listed" in result
    mock_auth.grant_permission.assert_awaited_once()
    runtime.execute_tool.assert_awaited_once_with(
        tool_name="list_dir",
        tool_args={"path": "/tmp/outside"},
        tool_call_id="call-1",
        config={"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
        state=None,
    )


@pytest.mark.asyncio
async def test_approved_grants_all_paths_of_compound_command():
    """复合命令多路径（authorization.all_paths）：批准后一次性全量授权，
    避免重执行对下一个未授权路径再次弹审批（连环审批根因）。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        pending = _pending_tool(
            authorization={
                "resource_path": "/tmp/outside-a",
                "action": "read",
                "all_paths": [
                    ["/tmp/outside-a", "read"],
                    ["/tmp/outside-b", "read"],
                ],
            }
        )
        await HITLOrchestrator.resolve_approved_tool_result(
            pending,
            {"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
        )

    granted = mock_auth.grant_permission.await_args_list
    paths = {call.kwargs["resource_path"] for call in granted}
    assert paths == {"/tmp/outside-a", "/tmp/outside-b"}
    assert all(call.kwargs["action"] == "read" for call in granted)
    assert all(call.kwargs["scope_type"] == "exact" for call in granted)


@pytest.mark.asyncio
async def test_dir_mode_grants_parent_prefix():
    """grant_mode=dir → 授权父目录（scope_type=prefix，递归命中）。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        mock_get_runtime.return_value.execute_tool = AsyncMock(return_value="done")

        pending = _pending_tool(
            authorization={
                "resource_path": "/outside/dir/sub/file.txt",
                "action": "read",
                "all_paths": [["/outside/dir/sub/file.txt", "read"]],
            }
        )
        await HITLOrchestrator.resolve_approved_tool_result(
            pending,
            {"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
            grant_mode="dir",
        )

    call = mock_auth.grant_permission.await_args
    assert call.kwargs["resource_path"] == "/outside/dir/sub"
    assert call.kwargs["scope_type"] == "prefix"


@pytest.mark.asyncio
async def test_dir_mode_root_level_path_falls_back_to_exact():
    """锐边守卫：根级路径（/x）的父目录是 / → prefix 授权 / 等于全盘放行，
    dir 模式必须降级为 exact。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        mock_get_runtime.return_value.execute_tool = AsyncMock(return_value="done")

        pending = _pending_tool(
            authorization={
                "resource_path": "/rootfile",
                "action": "read",
                "all_paths": [["/rootfile", "read"]],
            }
        )
        await HITLOrchestrator.resolve_approved_tool_result(
            pending,
            {"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
            grant_mode="dir",
        )

    call = mock_auth.grant_permission.await_args
    assert call.kwargs["resource_path"] == "/rootfile"
    assert call.kwargs["scope_type"] == "exact"


@pytest.mark.asyncio
async def test_rejected_marks_all_paths_dead():
    """复合命令拒绝：判死覆盖全部路径候选（拒绝一次，不再逐路径 ping-pong）。"""
    with (
        patch(
            "app.core.hitl.orchestrator.HITLOrchestrator.mark_thread_resource_rejected",
            AsyncMock(),
        ) as mock_mark,
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
    ):
        mock_auth_cls.return_value = AsyncMock()
        pending = _pending_tool(
            authorization={
                "resource_path": "/tmp/outside-a",
                "action": "read",
                "all_paths": [
                    ["/tmp/outside-a", "read"],
                    ["/tmp/outside-b", "read"],
                ],
            }
        )
        await HITLOrchestrator.resolve_approved_tool_result(
            pending,
            {"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
            "REJECTED",
            state=None,
            thread_id="t-1",
        )

    rejected_paths = {call.kwargs["resource_path"] for call in mock_mark.await_args_list}
    assert rejected_paths == {"/tmp/outside-a", "/tmp/outside-b"}


@pytest.mark.asyncio
async def test_free_text_input_not_treated_as_rejection():
    """无 authorization 的自由文本（ask_human text）输入 "REJECTED" 应原样返回，
    不得触发授权门控的拒绝语义。"""
    pending = _pending_tool(authorization=None)  # 非授权门控
    result = await HITLOrchestrator.resolve_approved_tool_result(
        pending,
        {"metadata": {"project_id": 120}},
        "REJECTED",
        state=None,
    )
    assert result == "REJECTED"
    assert not result.startswith("用户拒绝了")


@pytest.mark.asyncio
async def test_free_text_yes_not_treated_as_approval():
    """无 authorization 的自由文本输入 "yes" 应原样返回（不重执行、不授权）。"""
    pending = _pending_tool(authorization=None)
    result = await HITLOrchestrator.resolve_approved_tool_result(
        pending,
        {"metadata": {"project_id": 120}},
        "yes",
        state=None,
    )
    assert result == "yes"


@pytest.mark.asyncio
async def test_resume_args_override_injected_into_reexecution():
    """resume.args 声明（如宏确认的 skip_confirmation）在批准重执行时注入工具参数。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        pending = _pending_tool(
            name="run_macro",
            args={"macro_id": 7, "query": "u1"},
            resume={"args": {"skip_confirmation": True}},
        )
        await HITLOrchestrator.resolve_approved_tool_result(
            pending,
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
        )
    runtime.execute_tool.assert_awaited_once_with(
        tool_name="run_macro",
        tool_args={"macro_id": 7, "query": "u1", "skip_confirmation": True},
        tool_call_id="call-1",
        config={"metadata": {"project_id": 120}},
        state=None,
    )


@pytest.mark.asyncio
async def test_no_resume_no_override_injected():
    """无 resume 声明时参数与 config 原样透传（无默认豁免注入）。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        await HITLOrchestrator.resolve_approved_tool_result(
            _pending_tool(),
            {"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
        )
    runtime.execute_tool.assert_awaited_once_with(
        tool_name="list_dir",
        tool_args={"path": "/tmp/outside"},
        tool_call_id="call-1",
        config={"configurable": {"thread_id": "t-1"}, "metadata": {"project_id": 120}},
        state=None,
    )
    kwargs = runtime.execute_tool.await_args.kwargs
    assert "_skip_mcp_confirmation" not in kwargs["config"]
