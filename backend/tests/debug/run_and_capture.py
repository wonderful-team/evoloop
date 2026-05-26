#!/usr/bin/env python3
"""运行测试脚本并捕获输出"""
import subprocess
import sys
import os
import signal

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

# 运行脚本
proc = subprocess.Popen(
    [sys.executable, "test_execute_skill_713.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1  # 行缓冲
)

# 读取前70行
count = 0
for line in proc.stdout:
    print(line, end='')
    count += 1
    if count >= 70:
        break

# 杀掉进程
proc.send_signal(signal.SIGTERM)
proc.wait(timeout=2)
print("\n\n[进程已终止]")
