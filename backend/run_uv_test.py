#!/usr/bin/env python3
"""使用 uv run 运行测试脚本并设置超时"""
import subprocess
import sys
import os

os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

def load_env_file():
    from pathlib import Path
    env_path = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value

load_env_file()

# 使用 uv run 运行脚本
result = subprocess.run(
    ["uv", "run", "python", "test_execute_skill_713.py"],
    capture_output=True,
    text=True,
    timeout=30  # 30秒超时
)
print("STDOUT:")
print(result.stdout)
if result.stderr:
    print("\nSTDERR:")
    print(result.stderr)
