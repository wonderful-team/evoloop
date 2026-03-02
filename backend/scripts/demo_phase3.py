#!/usr/bin/env python3
"""
Demo script for Phase 3: Menu and Dock Operations.

This demonstrates the menu and dock control capabilities of EvoLoop.
"""
import asyncio

from app.infrastructure.drivers.macos_menu import macos_menu_driver
from app.domain.tools.environment.dock import list_dock_icons


def demo_menu_structure():
    """Demonstrate getting menu structure."""
    print("=" * 60)
    print("📋 Menu Structure Demo (Safari)")
    print("=" * 60)

    structure = macos_menu_driver.get_menu_structure("Safari")

    if structure:
        print(f"\nFound {len(structure)} top-level menus:")
        for menu, items in structure.items():
            print(f"\n{menu}:")
            for item in items[:8]:  # Show first 8 items
                print(f"  - {item}")
            if len(items) > 8:
                print(f"  ... and {len(items) - 8} more")
    else:
        print("Safari not running or not accessible")


def demo_menu_paths():
    """Demonstrate menu path examples."""
    print("\n" + "=" * 60)
    print("🔖 Menu Path Examples")
    print("=" * 60)

    examples = """
Menu paths use ">" as separator:

Common Safari Menus:
  File > New Window
  File > New Private Window
  File > Open Location...
  File > Close Window
  Edit > Copy
  Edit > Paste
  View > Zoom > In
  View > Zoom > Out
  View > Enter Full Screen
  History > Show All History
  Bookmarks > Add Bookmark...
  Safari > Preferences...
  Window > Minimize

Common WeChat Menus:
  文件 > 新建聊天
  文件 > 新的群聊
  编辑 > 复制
  编辑 > 粘贴
  查看 > 放大
  微信 > 偏好设置
"""
    print(examples)


def demo_common_actions():
    """Demonstrate common actions mapping."""
    print("=" * 60)
    print("⚡ Common Actions")
    print("=" * 60)

    actions = """
The perform_common_action tool automatically maps action names to menu paths:

  "new"          -> File > New / File > New Window
  "open"         -> File > Open
  "save"         -> File > Save
  "close"        -> File > Close
  "copy"         -> Edit > Copy
  "cut"          -> Edit > Cut
  "paste"        -> Edit > Paste
  "select_all"   -> Edit > Select All
  "undo"         -> Edit > Undo
  "redo"         -> Edit > Redo
  "preferences"  -> File/Edit/App > Preferences
  "quit"         -> File > Quit

Example:
  await perform_common_action(app_name="Safari", action="new")
  # Automatically finds and clicks "File > New Window"
"""
    print(actions)


async def demo_dock_listing():
    """Demonstrate listing Dock icons."""
    print("=" * 60)
    print("🚢 Dock Icons Demo")
    print("=" * 60)

    result = await list_dock_icons.ainvoke({})
    print(result)


def demo_integration():
    """Show integration examples."""
    print("\n" + "=" * 60)
    print("🔗 Complete Workflow Examples")
    print("=" * 60)

    workflow = """
Example 1: Open Safari and navigate to a website
  1. await click_dock_icon(app_name="Safari")
  2. await window_focus(app_name="Safari")
  3. await perform_common_action(app_name="Safari", action="new")
  4. await click_element(element_id="T1")  # Address bar
  5. await desktop_control(action="type_text", text="https://example.com")

Example 2: Check WeChat messages
  1. badge = await get_dock_badge(app_name="WeChat")
  2. if badge > 0:
  3.     await window_focus(app_name="WeChat")
  4.     await get_state_elements("com.tencent.xinWeChat")
  5.     await click_element(element_id="B1")  # First conversation

Example 3: Use menu to export a file
  1. await window_focus(app_name="Pages")
  2. await click_menu_item(app_name="Pages", menu_path="File > Export To > PDF")
  3. await click_element(element_id="B2")  # Save button

Example 4: Check notifications across apps
  1. dock = await list_dock_icons()
  2. for app in ["WeChat", "Mail", "Slack"]:
  3.     badge = await get_dock_badge(app_name=app)
  4.     if badge:
  5.         print(f"{app} has {badge} notifications")
"""
    print(workflow)


async def main():
    """Run all demos."""
    demo_menu_structure()
    demo_menu_paths()
    demo_common_actions()
    await demo_dock_listing()
    demo_integration()

    print("\n" + "=" * 60)
    print("✨ Phase 3 Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
