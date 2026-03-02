
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.tools.environment.mobile import mobile_control

print(f"Tool: {mobile_control}")
print(f"Tool Type: {type(mobile_control)}")
print(f"Has func: {hasattr(mobile_control, 'func')}")
if hasattr(mobile_control, 'func'):
    print(f"Func: {mobile_control.func}")
print(f"Attributes: {dir(mobile_control)}")
