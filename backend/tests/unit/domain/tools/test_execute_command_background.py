"""
Unit tests for execute_command background mode integration.

Tests BackgroundTaskManager integration with execute_command.

pytest tests/unit/domain/tools/test_execute_command_background.py -v
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from app.core.tools.background import task_manager, TaskType, TaskStatus, CreateBackgroundTaskRequest
from app.domain.tools.execution import (
    execute_command,
    query_command_status,
    cancel_command,
    _get_thread_id,
)


class TestExecuteCommandBackground:
    """Test execute_command with background mode."""

    @pytest.fixture(autouse=True)
    async def cleanup_tasks(self):
        """Clean up tasks after each test."""
        yield
        # Clear all tasks after test
        task_manager._tasks.clear()
        task_manager._thread_index.clear()
        task_manager._tool_index.clear()
        task_manager._status_index.clear()

    @pytest.mark.asyncio
    async def test_execute_command_background_creates_task(self):
        """Test that background=True creates a task."""
        # Mock the background execution to avoid actually running command
        with patch('app.domain.tools.execution.background.run_command_background') as mock_run, \
             patch('app.domain.tools.execution.background.get_thread_id', return_value="test-thread-1"):
            mock_run.return_value = asyncio.Future()
            mock_run.return_value.set_result(None)
            
            result = await execute_command.ainvoke({
                "command": "echo hello",
                "background": True,
                "timeout": 60,
            })
            
            # Verify task was created
            assert "Background task started" in result
            assert "任务ID:" in result
            assert "查询状态:" in result
            
            # Verify task exists in manager
            tasks = task_manager.get_thread_tasks("test-thread-1")
            assert len(tasks) == 1
            assert tasks[0].tool_name == "execute_command"
            assert tasks[0].task_type == TaskType.COMMAND
            assert tasks[0].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_execute_command_sync_mode_unchanged(self):
        """Test that sync mode (background=False) still works."""
        with patch('app.domain.tools.execution.execute.execute_smart') as mock_exec:
            mock_exec.return_value = "Command Succeeded\nhello output"
            
            result = await execute_command.ainvoke({
                "command": "echo hello",
                "background": False,
                "timeout": 60,
                "config": None
            })
            
            assert "Command Succeeded" in result
            assert "hello output" in result

    @pytest.mark.asyncio
    async def test_query_command_status_not_found(self):
        """Test querying non-existent task."""
        result = await query_command_status.ainvoke({"task_id": "cmd-nonexistent"})
        
        assert "not found" in result.lower()
        assert "cmd-nonexistent" in result

    @pytest.mark.asyncio
    async def test_query_command_status_running(self):
        """Test querying running task."""
        # Create a task
        task = await task_manager.create_task(
            CreateBackgroundTaskRequest(
                task_type=TaskType.COMMAND,
                title="测试命令",
                tool_name="execute_command",
                thread_id="test-thread",
            )
        )
        
        # Mark as running
        await task_manager.start_task(task.task_id, process_id=12345)
        
        # Add some output
        task_manager.append_output(task.task_id, "Line 1")
        task_manager.append_output(task.task_id, "Line 2")
        
        # Query
        result = await query_command_status.ainvoke({"task_id": task.task_id, "output_lines": 10})
        
        assert "▶️" in result or "RUNNING" in result or "运行" in result
        assert "测试命令" in result
        assert "进程ID: 12345" in result
        assert "Line 1" in result
        assert "Line 2" in result

    @pytest.mark.asyncio
    async def test_query_command_status_completed(self):
        """Test querying completed task."""
        # Create and complete task
        task = await task_manager.create_task(
            CreateBackgroundTaskRequest(
                task_type=TaskType.COMMAND,
                title="测试命令",
                tool_name="execute_command",
                thread_id="test-thread",
            )
        )
        
        await task_manager.start_task(task.task_id)
        task_manager.append_output(task.task_id, "Success output")
        await task_manager.complete_task(task.task_id, result={"exit_code": 0})
        
        # Query
        result = await query_command_status.ainvoke({"task_id": task.task_id})
        
        assert "✅" in result or "COMPLETED" in result or "成功" in result
        assert "Success output" in result
        assert "Command execution successful" in result

    @pytest.mark.asyncio
    async def test_query_command_status_failed(self):
        """Test querying failed task."""
        task = await task_manager.create_task(
            CreateBackgroundTaskRequest(
                task_type=TaskType.COMMAND,
                title="测试命令",
                tool_name="execute_command",
                thread_id="test-thread",
            )
        )
        
        await task_manager.start_task(task.task_id)
        await task_manager.fail_task(task.task_id, error="Command not found")
        
        result = await query_command_status.ainvoke({"task_id": task.task_id})
        
        assert "❌" in result or "FAILED" in result or "失败" in result
        assert "Command not found" in result

    @pytest.mark.asyncio
    async def test_cancel_command_success(self):
        """Test cancelling a running task."""
        task = await task_manager.create_task(
            CreateBackgroundTaskRequest(
                task_type=TaskType.COMMAND,
                title="测试命令",
                tool_name="execute_command",
                thread_id="test-thread",
            )
        )
        
        await task_manager.start_task(task.task_id, process_id=12345)
        
        # Mock os.killpg to avoid actually killing anything
        with patch('os.killpg') as mock_kill:
            result = await cancel_command.ainvoke({"task_id": task.task_id, "force": False})
            
            assert "✅" in result or "已取消" in result or "cancelled" in result.lower()
            assert task.task_id in result
            
            # Verify task status
            task = task_manager.get_task(task.task_id)
            assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_command_not_found(self):
        """Test cancelling non-existent task."""
        result = await cancel_command.ainvoke({"task_id": "cmd-nonexistent"})
        
        assert "not found" in result.lower()
        assert "cmd-nonexistent" in result

    @pytest.mark.asyncio
    async def test_cancel_command_already_completed(self):
        """Test cancelling already completed task."""
        task = await task_manager.create_task(
            CreateBackgroundTaskRequest(
                task_type=TaskType.COMMAND,
                title="测试命令",
                tool_name="execute_command",
                thread_id="test-thread",
            )
        )
        
        await task_manager.start_task(task.task_id)
        await task_manager.complete_task(task.task_id)
        
        result = await cancel_command.ainvoke({"task_id": task.task_id})
        
        assert "⚠️" in result or "已完成" in result or "completed" in result.lower()

    @pytest.mark.asyncio
    async def test_get_thread_id_from_config(self):
        """Test extracting thread_id from config."""
        config = {"configurable": {"thread_id": "test-123"}}
        thread_id = _get_thread_id(config)
        
        assert thread_id == "test-123"

    @pytest.mark.asyncio
    async def test_get_thread_id_fallback(self):
        """Test thread_id fallback when not in config."""
        with patch('app.domain.tools.execution._utils.ContextManager') as mock_ctx:
            mock_ctx.current.return_value.thread_id = "fallback-thread"
            
            thread_id = _get_thread_id(None)
            
            assert thread_id == "fallback-thread"


class TestExecuteCommandIntegration:
    """Integration tests for execute_command with real execution."""

    @pytest.mark.asyncio
    async def test_quick_command_sync_execution(self):
        """Test that quick commands work in sync mode."""
        result = await execute_command.ainvoke({
            "command": "echo 'hello world'",
            "background": False,
            "timeout": 10,
            "config": None
        })
        
        assert "Succeeded" in result or "hello world" in result

    @pytest.mark.asyncio
    async def test_background_mode_task_lifecycle(self):
        """Test full lifecycle of background task."""
        # Start background task
        with patch('app.domain.tools.execution.background.run_command_background') as mock_run:
            future = asyncio.Future()
            future.set_result(None)
            mock_run.return_value = future
            
            result = await execute_command.ainvoke({
                "command": "sleep 1 && echo done",
                "background": True,
                "timeout": 300,
                "config": {"configurable": {"thread_id": "lifecycle-test"}}
            })
            
            # Extract task ID from result
            import re
            match = re.search(r'任务ID: `([^`]+)`', result)
            assert match, f"Task ID not found in result: {result}"
            task_id = match.group(1)
            
            # Verify task exists
            task = task_manager.get_task(task_id)
            assert task is not None
            assert task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_timeout_parameter_validation(self):
        """Test that timeout is clamped to valid range."""
        # Test minimum (should be 10)
        with patch('app.domain.tools.execution.execute.execute_smart') as mock_exec:
            mock_exec.return_value = ""
            
            await execute_command.ainvoke({
                "command": "echo test",
                "background": False,
                "timeout": 5,  # Below minimum
                "config": None
            })
            
            # Check that timeout was clamped to at least 10
            call_args = mock_exec.call_args
            assert call_args[0][1] >= 10  # positional arg: timeout

        # Test maximum (should be 3600)
        with patch('app.domain.tools.execution.execute.execute_smart') as mock_exec:
            mock_exec.return_value = ""
            
            await execute_command.ainvoke({
                "command": "echo test",
                "background": False,
                "timeout": 5000,  # Above maximum
                "config": None
            })
            
            call_args = mock_exec.call_args
            assert call_args[0][1] <= 3600  # positional arg: timeout
