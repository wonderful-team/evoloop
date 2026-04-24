"""
Pytest 全局配置

确保 backend/ 目录在 sys.path 中，使 import app 能正确解析。
"""
import sys
from pathlib import Path

# 将项目根目录的 backend/ 加入 Python 路径
BACKEND_DIR = Path(__file__).parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
