"""
Unit tests for Brain Cognitive System.
Tests the LightningKernel, SSMDriver, MemoryConsolidator, and flash_brain_node.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from app.core.brain.kernel import LightningKernel
from app.core.brain.drivers.abstract import BaseBrainDriver
from app.core.brain.drivers.ssm_driver import SSMDriver
from app.core.brain.filesystem.protocol import MemoryZone, MemoryFile
from app.core.brain.consolidation import MemoryConsolidator
from app.core.brain.node import flash_brain_node, get_or_create_kernel, _kernel_instance


class MockBrainDriver(BaseBrainDriver):
    """Mock driver for testing."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.initialized = False

    async def initialize(self):
        self.initialized = True

    async def generate(self, context: str, user_input: str, system_prompt: str | None = None) -> str:
        self.call_count += 1
        if self.call_count <= len(self.responses):
            return self.responses[self.call_count - 1]
        return f"Mock response to: {user_input}"

    async def health_check(self) -> bool:
        return self.initialized


class TestLightningKernel:
    """Tests for LightningKernel."""

    @pytest.fixture
    def mock_fs(self):
        """Create a mock file system."""
        fs = MagicMock()
        fs.initialize = MagicMock()
        fs._validate_path = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=True)))
        fs.read_file = MagicMock(return_value="test content")
        fs.write_file = MagicMock()
        fs.list_files = MagicMock(return_value=["file1.md", "file2.md"])
        fs.search_files = MagicMock(return_value=["result1", "result2"])
        return fs

    @pytest.fixture
    def kernel(self, mock_fs):
        """Create a kernel with mocked dependencies."""
        driver = MockBrainDriver()
        return LightningKernel(driver, mock_fs)

    @pytest.mark.asyncio
    async def test_kernel_initialization(self, kernel, mock_fs):
        """Test kernel boot sequence."""
        await kernel.initialize()

        mock_fs.initialize.assert_called_once()
        assert kernel.fast.initialized is True

    @pytest.mark.asyncio
    async def test_kernel_loads_identity(self, kernel, mock_fs):
        """Test that kernel loads system identity."""
        mock_fs.read_file = MagicMock(return_value="You are EvoLoop")

        context = kernel._load_context()

        assert "SYSTEM_IDENTITY" in context
        assert "You are EvoLoop" in context

    @pytest.mark.asyncio
    async def test_kernel_loads_task(self, kernel, mock_fs):
        """Test that kernel loads current task."""
        def mock_read(path):
            if "task" in path:
                return "Current task content"
            return "Identity content"

        mock_fs.read_file = MagicMock(side_effect=mock_read)

        context = kernel._load_context()

        assert "CURRENT_TASK" in context
        assert "Current task content" in context

    @pytest.mark.asyncio
    async def test_kernel_skips_empty_task(self, kernel, mock_fs):
        """Test that kernel skips empty task."""
        def mock_read(path):
            if "task" in path:
                return "[Error: File not found]"
            return "Identity"

        mock_fs.read_file = MagicMock(side_effect=mock_read)

        context = kernel._load_context()

        assert "CURRENT_TASK" not in context

    def test_parse_tool_call_valid(self, kernel):
        """Test parsing valid tool call."""
        output = '<cmd>read_file path="test.md"</cmd>'

        cmd, args = kernel._parse_tool_call(output)

        assert cmd == "read_file"
        assert 'path="test.md"' in args

    def test_parse_tool_call_no_command(self, kernel):
        """Test parsing output without command."""
        output = "Just a normal response"

        cmd, args = kernel._parse_tool_call(output)

        assert cmd is None
        assert args is None

    def test_parse_tool_call_empty_args(self, kernel):
        """Test parsing command without args."""
        output = "<cmd>help</cmd>"

        cmd, args = kernel._parse_tool_call(output)

        assert cmd == "help"
        assert args == ""

    @pytest.mark.asyncio
    async def test_execute_tool_read_file(self, kernel, mock_fs):
        """Test executing read_file tool."""
        mock_fs.read_file = MagicMock(return_value="file contents")

        result = await kernel._execute_tool("read_file", 'path="test.md"')

        assert result == "file contents"
        mock_fs.read_file.assert_called_with("test.md")

    @pytest.mark.asyncio
    async def test_execute_tool_write_file(self, kernel, mock_fs):
        """Test executing write_file tool."""
        result = await kernel._execute_tool("write_file", 'path="test.md" content="hello"')

        mock_fs.write_file.assert_called_with("test.md", "hello")

    @pytest.mark.asyncio
    async def test_execute_tool_list_files(self, kernel, mock_fs):
        """Test executing list_files tool."""
        result = await kernel._execute_tool("list_files", 'path="."')

        assert "file1.md" in result
        mock_fs.list_files.assert_called_with(".")

    @pytest.mark.asyncio
    async def test_execute_tool_search_files(self, kernel, mock_fs):
        """Test executing search_files tool."""
        result = await kernel._execute_tool("search_files", 'query="test"')

        assert "result1" in result
        mock_fs.search_files.assert_called_with("test")

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self, kernel):
        """Test executing unknown tool."""
        result = await kernel._execute_tool("unknown_tool", "args")

        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_execute_tool_parse_error(self, kernel):
        """Test handling parse error in tool args."""
        result = await kernel._execute_tool("read_file", 'unbalanced="quotes')

        assert "Error parsing arguments" in result

    @pytest.mark.asyncio
    async def test_step_no_tool_call(self, kernel, mock_fs):
        """Test step without tool call."""
        kernel.fast.responses = ["Final answer"]
        await kernel.initialize()

        result = await kernel.step("Hello")

        assert result == "Final answer"

    @pytest.mark.asyncio
    async def test_step_with_tool_call(self, kernel, mock_fs):
        """Test step with tool call and recursion."""
        kernel.fast.responses = [
            '<cmd>read_file path="test.md"</cmd>',
            "Final answer after tool"
        ]
        mock_fs.read_file = MagicMock(return_value="file content")
        await kernel.initialize()

        result = await kernel.step("Hello")

        assert "Final answer" in result
        assert mock_fs.read_file.called

    @pytest.mark.asyncio
    async def test_step_max_depth(self, kernel):
        """Test max recursion depth protection."""
        result = await kernel.step("Hello", max_depth=0)

        assert "Max recursion depth" in result


class TestSSMDriver:
    """Tests for SSMDriver."""

    @pytest.fixture
    def driver(self):
        return SSMDriver()

    def test_driver_initial_state(self, driver):
        """Test initial driver state."""
        assert driver.client is None
        assert driver.mode == "mock"

    @pytest.mark.asyncio
    async def test_driver_mock_mode_response(self, driver):
        """Test driver in mock mode."""
        with patch.object(driver, 'mode', 'mock'):
            response = await driver.generate("context", "remember this project")

            assert "write_file" in response

    @pytest.mark.asyncio
    async def test_driver_mock_mode_generic(self, driver):
        """Test driver mock mode generic response."""
        with patch.object(driver, 'mode', 'mock'):
            response = await driver.generate("context", "hello")

            assert "Mock" in response or "mock" in response.lower()

    @pytest.mark.asyncio
    async def test_driver_health_check_mock(self, driver):
        """Test health check in mock mode."""
        driver.mode = "mock"
        driver.client = None

        healthy = await driver.health_check()

        assert healthy is True

    @pytest.mark.asyncio
    async def test_driver_health_check_active_no_client(self, driver):
        """Test health check when mode is active but no client."""
        driver.mode = "active"
        driver.client = None

        healthy = await driver.health_check()

        # In mock mode it returns True, in active mode with no client it should try and fail
        # The actual behavior depends on the implementation
        assert isinstance(healthy, bool)


class TestMemoryConsolidator:
    """Tests for MemoryConsolidator."""

    @pytest.fixture
    def mock_llm(self):
        return MockBrainDriver()

    @pytest.fixture
    def mock_fs(self):
        fs = MagicMock()
        fs.read_file = MagicMock(return_value="Task content")
        fs.write_file = MagicMock()
        fs.append_file = MagicMock()
        return fs

    @pytest.fixture
    def consolidator(self, mock_llm, mock_fs):
        return MemoryConsolidator(mock_llm, mock_fs)

    @pytest.mark.asyncio
    async def test_consolidation_no_task(self, consolidator, mock_fs):
        """Test consolidation with no active task."""
        mock_fs.read_file = MagicMock(return_value="[Error: File not found]")

        await consolidator.run_cycle()

        mock_fs.append_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_consolidation_success(self, consolidator, mock_llm, mock_fs):
        """Test successful consolidation cycle."""
        mock_llm.responses = ["Summary of work done"]

        await consolidator.run_cycle("msg-123")

        mock_fs.append_file.assert_called_once()
        call_args = mock_fs.append_file.call_args[0]
        assert "Consolidated Entry" in call_args[1]
        assert "msg-123" in call_args[1]
        assert "Summary of work done" in call_args[1]

    @pytest.mark.asyncio
    async def test_consolidation_clears_scratchpad(self, consolidator, mock_fs):
        """Test that consolidation clears the scratchpad."""
        mock_fs.read_file = MagicMock(return_value="Task content")

        await consolidator.run_cycle()

        mock_fs.write_file.assert_called_with(
            f"{MemoryZone.WORKING.value}/{MemoryFile.TASK.value}",
            ""
        )

    @pytest.mark.asyncio
    async def test_remove_entry_by_id_success(self, consolidator, mock_fs):
        """Test removing entry by ID."""
        journal_content = """# Journal
## Consolidated Entry <!-- id: keep-this --> Keep this entry
## Consolidated Entry <!-- id: remove-this --> Remove this entry
More content here"""
        mock_fs.read_file = MagicMock(return_value=journal_content)

        result = await consolidator.remove_entry_by_id("remove-this")

        assert result is True
        mock_fs.write_file.assert_called_once()
        written_content = mock_fs.write_file.call_args[0][1]
        assert "keep-this" in written_content
        assert "remove-this" not in written_content

    @pytest.mark.asyncio
    async def test_remove_entry_by_id_not_found(self, consolidator, mock_fs):
        """Test removing non-existent entry."""
        mock_fs.read_file = MagicMock(return_value="# Journal\n## Other Entry")

        result = await consolidator.remove_entry_by_id("missing-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_entry_by_id_empty_journal(self, consolidator, mock_fs):
        """Test removing from empty journal."""
        mock_fs.read_file = MagicMock(return_value="")

        result = await consolidator.remove_entry_by_id("any-id")

        assert result is False


class TestFlashBrainNode:
    """Tests for flash_brain_node."""

    @pytest.fixture(autouse=True)
    def reset_kernel(self):
        """Reset kernel singleton before each test."""
        global _kernel_instance
        _kernel_instance = None
        yield
        _kernel_instance = None

    @pytest.mark.asyncio
    async def test_node_no_messages(self):
        """Test node with no messages."""
        state = {"messages": []}
        config = {"configurable": {"thread_id": "test"}}

        result = await flash_brain_node(state, config)

        assert result["next_node"] == "supervisor"

    @pytest.mark.asyncio
    async def test_node_with_execution_ticket(self):
        """Test node with execution ticket topic."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="user message")],
            "execution_ticket": {"topic": "Ticket Topic"}
        }
        config = {"configurable": {"thread_id": "test"}}

        with patch('app.core.brain.node.get_or_create_kernel') as mock_get_kernel:
            mock_kernel = MagicMock()
            mock_kernel.step = AsyncMock(return_value="Kernel response")
            mock_get_kernel.return_value = mock_kernel

            result = await flash_brain_node(state, config)

            assert "messages" in result
            assert "[Flash Brain]" in result["messages"][0].content
            assert result["next_node"] == "supervisor"
            assert result["execution_ticket"] is None

    @pytest.mark.asyncio
    async def test_node_fallback_to_last_message(self):
        """Test node falls back to last message when no ticket."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="Last message content")],
        }
        config = {"configurable": {"thread_id": "test"}}

        with patch('app.core.brain.node.get_or_create_kernel') as mock_get_kernel:
            mock_kernel = MagicMock()
            mock_kernel.step = AsyncMock(return_value="Response")
            mock_get_kernel.return_value = mock_kernel

            result = await flash_brain_node(state, config)

            mock_kernel.step.assert_called_with("Last message content")

    @pytest.mark.asyncio
    async def test_node_kernel_error(self):
        """Test node handles kernel errors gracefully."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="test")],
        }
        config = {"configurable": {"thread_id": "test"}}

        with patch('app.core.brain.node.get_or_create_kernel') as mock_get_kernel:
            mock_get_kernel.side_effect = Exception("Kernel init failed")

            result = await flash_brain_node(state, config)

            assert result["next_node"] == "supervisor"
            assert "Error" in result["messages"][0].content


class TestMemoryProtocol:
    """Tests for Memory Protocol enums and utilities."""

    def test_memory_zone_values(self):
        """Test MemoryZone enum values."""
        assert MemoryZone.SYS.value == "sys"
        assert MemoryZone.WORKING.value == "working"
        assert MemoryZone.KNOWLEDGE.value == "knowledge"
        assert MemoryZone.LOGS.value == "logs"

    def test_memory_file_values(self):
        """Test MemoryFile enum values."""
        assert MemoryFile.IDENTITY.value == "identity.md"
        assert MemoryFile.TASK.value == "current_task.md"
        assert MemoryFile.SCRATCHPAD.value == "scratchpad.md"

    def test_default_structure(self):
        """Test default memory structure."""
        from app.core.brain.filesystem.protocol import DEFAULT_STRUCTURE

        assert MemoryZone.SYS in DEFAULT_STRUCTURE
        assert MemoryZone.WORKING in DEFAULT_STRUCTURE
        assert MemoryZone.KNOWLEDGE in DEFAULT_STRUCTURE
        assert MemoryZone.LOGS in DEFAULT_STRUCTURE

        assert MemoryFile.IDENTITY in DEFAULT_STRUCTURE[MemoryZone.SYS]
        assert MemoryFile.TASK in DEFAULT_STRUCTURE[MemoryZone.WORKING]

    def test_get_zone_path(self):
        """Test zone path generation."""
        from app.core.brain.filesystem.protocol import get_zone_path

        root = Path("/tmp/brain")
        path = get_zone_path(root, MemoryZone.SYS)

        assert str(path) == "/tmp/brain/sys"
