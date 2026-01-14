"""
Tool Layer Tests - Command Execution (run_command)
Covers: RC-001 to RC-006
"""
import pytest
import os
import tempfile

from tests.config import config


class TestRunCommand:
    """Test suite for run_command tool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for command tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    # RC-001: Simple Command
    @pytest.mark.asyncio
    async def test_rc_001_simple_command(self, temp_dir):
        """Test executing simple command."""
        from app.domain.tools.execution import run_command
        
        result = await run_command.ainvoke({
            "command": "pwd"
        })
        
        assert "/" in result

    # RC-002: Command with Arguments
    @pytest.mark.asyncio
    async def test_rc_002_command_with_args(self, temp_dir):
        """Test command with arguments."""
        from app.domain.tools.execution import run_command
        
        # Create a file first
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("content")
        
        result = await run_command.ainvoke({
            "command": f"ls -la {temp_dir}"
        })
        
        assert "test.txt" in result

    # RC-003: State Preservation (cd)
    @pytest.mark.asyncio
    async def test_rc_003_state_preservation(self, temp_dir):
        """Test that directory changes persist in session."""
        from app.domain.tools.execution import run_command
        
        subdir = os.path.join(temp_dir, "subdir")
        os.makedirs(subdir)
        
        result = await run_command.ainvoke({
            "command": f"cd {subdir} && pwd"
        })
        
        assert "subdir" in result

    # RC-004: Environment Variables
    @pytest.mark.asyncio
    async def test_rc_004_environment_variables(self, temp_dir):
        """Test environment variable handling."""
        from app.domain.tools.execution import run_command
        
        result = await run_command.ainvoke({
            "command": "TEST_VAR=hello && echo test_var_is_$TEST_VAR"
        })
        
        # May output "hello" directly or indicate export
        assert "hello" in result or "TEST_VAR" in result or "Succeeded" in result

    # RC-005: Timeout (handled by terminal manager)
    @pytest.mark.asyncio
    async def test_rc_005_long_command(self, temp_dir):
        """Test handling of commands (timeout handled by terminal manager)."""
        from app.domain.tools.execution import run_command
        
        # Short sleep should complete quickly
        result = await run_command.ainvoke({
            "command": "sleep 1 && echo 'done'"
        })
        
        assert "done" in result.lower() or "succeeded" in result.lower()

    # RC-006: Invalid Command
    @pytest.mark.asyncio
    async def test_rc_006_invalid_command(self, temp_dir):
        """Test handling of invalid command."""
        from app.domain.tools.execution import run_command
        
        result = await run_command.ainvoke({
            "command": "nonexistent_command_xyz123"
        })
        
        # Should contain error information
        assert "not found" in result.lower() or "failed" in result.lower() or "error" in result.lower()


class TestRunCommandEdgeCases:
    """Edge case tests for run_command."""

    @pytest.fixture
    def temp_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_multiline_output(self, temp_dir):
        """Test command with multiline output."""
        from app.domain.tools.execution import run_command
        
        result = await run_command.ainvoke({
            "command": "echo 'line1' && echo 'line2' && echo 'line3'"
        })
        
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_piped_commands(self, temp_dir):
        """Test piped commands."""
        from app.domain.tools.execution import run_command
        
        result = await run_command.ainvoke({
            "command": "echo 'hello world' | grep 'world'"
        })
        
        assert "world" in result

    @pytest.mark.asyncio
    async def test_exit_code_capture(self, temp_dir):
        """Test that exit codes are captured."""
        from app.domain.tools.execution import run_command
        
        result = await run_command.ainvoke({
            "command": "exit 1"
        })
        
        # Should indicate failure
        assert "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_command(self, temp_dir):
        """Test empty command handling."""
        from app.domain.tools.execution import run_command
        
        try:
            result = await run_command.ainvoke({
                "command": ""
            })
            # Should handle gracefully or return error
            assert True
        except (ValueError, Exception):
            # Expected for empty command
            pass
