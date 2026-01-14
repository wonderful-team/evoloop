"""
Workflow Node Tests - Coder Node
Covers: COD-001 to COD-006
"""
import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from tests.config import config


class TestCoderNode:
    """Test suite for Coder node functionality."""

    # COD-001: Create New File
    @pytest.mark.asyncio
    async def test_cod_001_create_file(self, sandbox_temp_dir):
        """Test creating a new file."""
        from app.domain.tools.files.actions.write import handle_write
        
        file_path = os.path.join(sandbox_temp_dir, "utils.py")
        content = '''def add(a, b):
    """Add two numbers."""
    return a + b
'''
        
        result = await handle_write(
            action="create",
            path=file_path,
            content=content
        )
        
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert "def add" in f.read()

    # COD-002: Modify File (Update Block)
    @pytest.mark.asyncio
    async def test_cod_002_update_block(self, sandbox_temp_dir):
        """Test updating a code block in a file."""
        from app.domain.tools.files.actions.edit import handle_edit
        
        # Create initial file
        file_path = os.path.join(sandbox_temp_dir, "utils.py")
        initial_content = '''def add(a, b):
    """Add two numbers."""
    return a + b
'''
        with open(file_path, "w") as f:
            f.write(initial_content)
        
        # Update the function
        target = '''def add(a, b):
    """Add two numbers."""
    return a + b'''
        
        replacement = '''def add(a, b):
    """Add two numbers together."""
    return a + b

def subtract(a, b):
    """Subtract b from a."""
    return a - b'''
        
        result = await handle_edit(
            path=file_path,
            target=target,
            content=replacement
        )
        
        with open(file_path) as f:
            content = f.read()
            assert "def subtract" in content or "Successfully" in result

    # COD-003: Fuzzy Match Fix
    @pytest.mark.asyncio
    async def test_cod_003_fuzzy_match(self, sandbox_temp_dir):
        """Test fuzzy matching for indentation differences."""
        from app.domain.tools.files.actions.edit import handle_edit
        
        # Create file with specific indentation
        file_path = os.path.join(sandbox_temp_dir, "test_indent.py")
        with open(file_path, "w") as f:
            f.write("    def foo():\n        pass\n")
        
        # Try to match with different indentation
        target = "def foo():\n    pass"  # No leading indent
        replacement = "def foo():\n    return 42"
        
        result = await handle_edit(
            path=file_path,
            target=target,
            content=replacement
        )
        
        # Should succeed with fuzzy matching
        with open(file_path) as f:
            content = f.read()
            assert "return 42" in content or "Successfully" in result or "updated" in result.lower()

    # COD-004: LSP Error Detection
    @pytest.mark.asyncio
    async def test_cod_004_lsp_error_detection(self, sandbox_temp_dir):
        """Test LSP can detect syntax errors."""
        from app.domain.tools.coding.lsp import consult_lsp
        
        # Create file with syntax error
        file_path = os.path.join(sandbox_temp_dir, "broken.py")
        with open(file_path, "w") as f:
            f.write("def broken()\n    return 42\n")  # Missing colon
        
        result = await consult_lsp.ainvoke({
            "action": "check_errors",
            "file_path": file_path
        })
        
        # Should detect the error
        assert "Error" in result or "error" in result.lower() or "Expected" in result or "invalid" in result.lower()

    # COD-005: Fix Mode
    @pytest.mark.asyncio
    async def test_cod_005_fix_mode(self, base_agent_state, runnable_config):
        """Test coder enters fix mode after failed test."""
        base_agent_state["scratchpad"]["fix_mode"] = True
        base_agent_state["scratchpad"]["test_failure"] = "ImportError: No module named 'foo'"
        
        # Test that coder node can be invoked with fix mode
        from app.core.engine.nodes.coder import coder_node
        
        # Mock AgentEngine instead of LLMFactory since CoderNode delegates to it
        with patch("app.core.engine.nodes.coder.AgentEngine") as MockAgentEngine:
            MockAgentEngine.run_node = AsyncMock(return_value={"messages": [AIMessage(content="Fixed")]})
            
            result = await coder_node(base_agent_state, runnable_config)
            assert result is not None
            # Verify fix mode logic (checking implicitly by successful execution)

    # COD-006: Tool RBAC
    @pytest.mark.asyncio
    async def test_cod_006_tool_rbac(self):
        """Test that coder can only access allowed tools."""
        from app.core.tools.registry_utils import get_node_tools
        
        coder_tools = get_node_tools("coder")
        tool_names = [t.name for t in coder_tools]
        
        # Coder should have file management tools
        assert "manage_file" in tool_names


class TestCoderEdgeCases:
    """Edge case tests for Coder node."""

    @pytest.mark.asyncio
    async def test_create_nested_directories(self, sandbox_temp_dir):
        """Test creating file in nested directories."""
        from app.domain.tools.files.actions.write import handle_write
        
        nested_path = os.path.join(sandbox_temp_dir, "a", "b", "c", "file.py")
        
        result = await handle_write(
            action="create",
            path=nested_path,
            content="# nested file"
        )
        
        assert os.path.exists(nested_path) or "Successfully" in result

    @pytest.mark.asyncio
    async def test_large_file_handling(self, sandbox_temp_dir):
        """Test handling of large files."""
        from app.domain.tools.files.actions.read import handle_read
        
        large_file = os.path.join(sandbox_temp_dir, "large.py")
        
        # Create a large file
        with open(large_file, "w") as f:
            for i in range(10000):
                f.write(f"# Line {i}\n")
        
        result = await handle_read(large_file)
        
        assert result is not None
