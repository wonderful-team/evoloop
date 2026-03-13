#!/usr/bin/env python3
"""执行测试脚本并设置超时"""
import subprocess
import sys

result = subprocess.run(
    ["python", "test_execute_skill_713.py"],
    capture_output=True,
    text=True,
    timeout=20
)
print(result.stdout)
print(result.stderr, file=sys.stderr)
