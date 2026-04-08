#!/usr/bin/env python3
"""
Standalone test for sudo security hook logic.
Tests the regex patterns without requiring full app dependencies.
"""

import re
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


# Simulate the security hook logic
_ELEVATED_PRIVILEGE_PATTERNS = [
    (r"^\s*sudo\s+", "sudo", "管理员权限(sudo)"),
    (r"^\s*su\s+(-|\w+)", "su", "用户切换(su)"),
    (r"^\s*pkexec\s+", "pkexec", "权限提升(pkexec)"),
]

_DANGEROUS_PATTERNS = [
    (r"^\s*passwd\s*\w*", "passwd", "密码修改"),
]


@dataclass
class MockHookResult:
    success: bool = True
    block: bool = False
    message: Optional[str] = None


def check_command_security(command: str) -> MockHookResult:
    """Simulate the security check logic from security.py"""
    if not command:
        return MockHookResult(success=True)
    
    # Check elevated privilege patterns
    for pattern, cmd_type, description in _ELEVATED_PRIVILEGE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return MockHookResult(
                success=False,
                block=True,
                message=(
                    f"❌ 命令执行被阻止：需要{description}\n\n"
                    f"命令：`{command[:200]}{'...' if len(command) > 200 else ''}`\n\n"
                    f"当前执行环境不支持交互式密码输入，此类命令会导致超时且无明确错误提示。\n\n"
                    f"**建议操作**：\n"
                    f"1. 寻找无需{description}的替代方案\n"
                    f"2. 使用 `ask_human` 工具请求用户协助执行\n"
                    f"3. 如需长期使用，请配置免密 sudo 或使用容器环境"
                )
            )
    
    # Check dangerous patterns
    for pattern, cmd_type, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return MockHookResult(
                success=False,
                block=True,
                message=f"⚠️ 安全风险：{description}命令被阻止"
            )
    
    return MockHookResult(success=True)


def run_tests():
    """Run all security hook tests."""
    print("=" * 60)
    print("Testing Sudo Security Hook Logic")
    print("=" * 60)
    
    test_cases = [
        # (command, expected_blocked, description)
        ("sudo apt-get install nodejs", True, "Basic sudo command"),
        ("  sudo npm install", True, "Sudo with leading spaces"),
        ("sudo -i", True, "Sudo interactive"),
        ("su - root", True, "Su with dash"),
        ("su root", True, "Su without dash"),
        ("pkexec apt-get update", True, "Pkexec command"),
        ("passwd", True, "Passwd command"),
        ("passwd root", True, "Passwd with user"),
        ("npm install", False, "Normal npm command"),
        ("git status", False, "Git command"),
        ("cat /etc/sudoers", False, "Cat sudoers file (not executing sudo)"),
        ("echo sudo is useful", False, "Echo with sudo text"),
        ("docker ps", False, "Docker command"),
        ("ls -la", False, "List command"),
        ("sudo", False, "Sudo alone (not a command)"),  # This is edge case
    ]
    
    passed = 0
    failed = 0
    
    for command, expected_blocked, description in test_cases:
        result = check_command_security(command)
        is_blocked = result.block
        
        if is_blocked == expected_blocked:
            status = "✅ PASS"
            passed += 1
        else:
            status = "❌ FAIL"
            failed += 1
        
        action = "BLOCKED" if is_blocked else "ALLOWED"
        expected = "should be BLOCKED" if expected_blocked else "should be ALLOWED"
        
        print(f"\n{status} {description}")
        print(f"   Command: \"{command}\"")
        print(f"   Result: {action} (expected: {expected})")
        
        if is_blocked and result.message:
            print(f"   Message: {result.message.split(chr(10))[0]}")
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("✅ All tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
