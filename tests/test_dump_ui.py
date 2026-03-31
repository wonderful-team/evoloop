#!/usr/bin/env python3
"""Test Desktop dump_ui action"""
import asyncio
import sys
import os

sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")
os.chdir("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

from app.domain.tools.environment.desktop import desktop_control

async def test():
    print("\n🧪 Testing desktop_control dump_ui...")
    print("="*60)

    # Open Safari first
    await desktop_control.ainvoke({"action": "open_app", "app_name": "Safari"})
    await asyncio.sleep(1)

    # Test dump_ui
    result = await desktop_control.ainvoke({"action": "dump_ui"})
    print(f"Result: {result[:500]}...")

    if "UI Hierarchy" in result and "elements" in result:
        print("\n✅ dump_ui implemented correctly")
        return True
    else:
        print("\n❌ dump_ui not working")
        return False

if __name__ == "__main__":
    passed = asyncio.run(test())
    sys.exit(0 if passed else 1)
