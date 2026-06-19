"""
Test for sudo security hook.

This test verifies that commands with sudo/su/pkexec are properly blocked
before execution to prevent timeout issues.
"""

import asyncio
import importlib
import pytest
from app.core.engine.hooks import hook_system, HookEvent, HookContext, security


@pytest.fixture(autouse=True)
def setup_security_hooks():
    """Explicitly reload security hooks for testing because conftest.py clears them."""
    importlib.reload(security)


async def test_sudo_command_blocked():
    """Test that sudo commands are blocked by the security hook."""
    context = HookContext(
        thread_id="test-thread-123",
        tool_name="execute_command",
        tool_input={"command": "sudo apt-get install nodejs"},
        blackboard={},
    )
    
    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    
    assert result.block is True, "Sudo command should be blocked"
    assert "管理员权限" in result.message or "sudo" in result.message, "Error message should indicate permission issue"
    print(f"✅ Sudo command blocked: {result.message[:100]}...")


async def test_su_command_blocked():
    """Test that su commands are blocked."""
    context = HookContext(
        thread_id="test-thread-123",
        tool_name="execute_command",
        tool_input={"command": "su - root"},
        blackboard={},
    )
    
    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    
    assert result.block is True, "Su command should be blocked"
    print(f"✅ Su command blocked: {result.message[:100]}...")


async def test_pkexec_command_blocked():
    """Test that pkexec commands are blocked."""
    context = HookContext(
        thread_id="test-thread-123",
        tool_name="execute_command",
        tool_input={"command": "pkexec apt-get update"},
        blackboard={},
    )
    
    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    
    assert result.block is True, "Pkexec command should be blocked"
    print(f"✅ Pkexec command blocked: {result.message[:100]}...")


async def test_normal_command_allowed():
    """Test that normal commands are not blocked."""
    context = HookContext(
        thread_id="test-thread-123",
        tool_name="execute_command",
        tool_input={"command": "npm install"},
        blackboard={},
    )
    
    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    
    assert result.block is False, "Normal command should not be blocked"
    print(f"✅ Normal command allowed")


async def test_command_with_sudo_in_path():
    """Test that commands containing 'sudo' in path but not as command are allowed."""
    context = HookContext(
        thread_id="test-thread-123",
        tool_name="execute_command",
        tool_input={"command": "cat /etc/sudoers"},  # Reading sudoers file, not using sudo
        blackboard={},
    )
    
    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    
    # This should be allowed - it's reading a file, not executing sudo
    assert result.block is False, "Reading sudo-related files should not be blocked"
    print(f"✅ Command with 'sudo' in path allowed: cat /etc/sudoers")


async def test_normal_file_read_allowed():
    """Test that reading non-sensitive files is allowed."""
    context = HookContext(
        thread_id="test-thread-123",
        tool_name="view_file",
        tool_input={"args": {"AbsolutePath": "/workspace/evoloop/README.md"}},
        blackboard={},
    )
    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    assert result.block is False
    print(f"✅ Normal file read allowed")


async def main():
    """Run all tests."""
    print("Testing sudo and sensitive file security hooks...\n")
    
    try:
        await test_sudo_command_blocked()
        await test_su_command_blocked()
        await test_pkexec_command_blocked()
        await test_normal_command_allowed()
        await test_command_with_sudo_in_path()
        await test_sensitive_file_read_blocked()
        await test_normal_file_read_allowed()
        print("\n✅ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
