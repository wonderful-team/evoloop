import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.core.tools.registry import REGISTRY

print(f"Total tools in REGISTRY: {len(REGISTRY._tools)}")
for tool in REGISTRY._tools:
    print(f"- {tool.name}")
