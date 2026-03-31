#!/usr/bin/env python3
"""
测试：从 Accessibility Tree (AX Tree) 中提取快捷键信息

原理：macOS 的 Accessibility API 可能包含菜单项的快捷键信息
"""

import subprocess
import json
import re


def get_ax_tree_via_applescript():
    """
    使用 AppleScript 获取当前应用的 Accessibility Tree
    并尝试提取包含快捷键信息的元素
    """
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        set appName to name of frontApp
        
        set jsonOutput to "{"
        set jsonOutput to jsonOutput & "'app': '" & appName & "', "
        set jsonOutput to jsonOutput & "'menu_items': ["
        
        try
            tell frontApp
                -- 获取菜单栏
                set menuBarItems to every menu bar item of menu bar 1
                set itemCount to count of menuBarItems
                set itemIndex to 1
                
                repeat with menuItem in menuBarItems
                    set itemName to name of menuItem
                    
                    -- 尝试获取菜单项下的子菜单
                    try
                        set subMenus to every menu of menuItem
                        repeat with subMenu in subMenus
                            set menuItems to every menu item of subMenu
                            
                            repeat with mItem in menuItems
                                try
                                    set mName to name of mItem
                                    -- 尝试获取快捷键
                                    try
                                        set mShortcut to value of attribute "AXMenuItemCmdChar" of mItem
                                        set mModifiers to value of attribute "AXMenuItemCmdModifiers" of mItem
                                        
                                        set itemStr to "{'name': '" & mName & "', 'shortcut': '" & mShortcut & "', 'modifiers': " & mModifiers & "}"
                                        set jsonOutput to jsonOutput & itemStr
                                        
                                        if itemIndex < itemCount then
                                            set jsonOutput to jsonOutput & ", "
                                        end if
                                        set itemIndex to itemIndex + 1
                                    end try
                                end try
                            end repeat
                        end repeat
                    end try
                end repeat
            end tell
        on error errMsg
            set jsonOutput to jsonOutput & "'error': '" & errMsg & "'"
        end try
        
        set jsonOutput to jsonOutput & "]}"
        return jsonOutput
    end tell
    '''
    
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def get_ax_tree_via_pyobjc():
    """
    使用 PyObjC 直接调用 Accessibility API
    这是更底层的方式，可能能获取更多信息
    """
    try:
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication,
            AXUIElementCreateSystemWide,
        )
        from AppKit import NSWorkspace
        
        # 获取当前应用
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()
        pid = active_app.processIdentifier()
        
        print(f"当前应用: {active_app.localizedName()}")
        print(f"PID: {pid}")
        
        # 创建 AX 元素
        app_element = AXUIElementCreateApplication(pid)
        
        # 尝试获取菜单栏
        error, menu_bar = AXUIElementCopyAttributeValue(
            app_element, "AXMenuBar", None
        )
        
        if error == 0 and menu_bar:
            print("\n找到菜单栏，尝试获取菜单项...")
            
            # 获取菜单栏的子项
            error, children = AXUIElementCopyAttributeValue(
                menu_bar, "AXChildren", None
            )
            
            if error == 0 and children:
                shortcuts_found = []
                
                for child in children:
                    # 尝试获取菜单项的名称
                    error, name = AXUIElementCopyAttributeValue(
                        child, "AXTitle", None
                    )
                    
                    if error == 0 and name:
                        # 尝试获取快捷键
                        error, shortcut = AXUIElementCopyAttributeValue(
                            child, "AXMenuItemCmdChar", None
                        )
                        
                        if error == 0 and shortcut:
                            error, modifiers = AXUIElementCopyAttributeValue(
                                child, "AXMenuItemCmdModifiers", None
                            )
                            
                            shortcuts_found.append({
                                "name": str(name),
                                "shortcut": str(shortcut),
                                "modifiers": str(modifiers) if error == 0 else "unknown"
                            })
                
                return shortcuts_found
        
        return []
        
    except ImportError:
        print("PyObjC 未安装，跳过 PyObjC 测试")
        return None
    except Exception as e:
        print(f"PyObjC 测试失败: {e}")
        return None


def test_specific_apps():
    """
    测试特定应用的快捷键获取
    """
    apps_to_test = [
        ("Safari", "com.apple.Safari"),
        ("微信", "com.tencent.xinWeChat"),
        ("备忘录", "com.apple.Notes"),
        ("Finder", "com.apple.finder"),
    ]
    
    print("=" * 70)
    print("测试不同应用的快捷键获取")
    print("=" * 70)
    
    for app_name, bundle_id in apps_to_test:
        print(f"\n📱 测试应用: {app_name}")
        print("-" * 40)
        
        # 尝试激活应用
        script = f'''
        tell application "{app_name}"
            activate
            delay 1
        end tell
        '''
        subprocess.run(["osascript", "-e", script], timeout=5)
        
        # 获取 AX Tree
        result = get_ax_tree_via_applescript()
        print(f"结果: {result[:500]}..." if len(result) > 500 else f"结果: {result}")


def analyze_existing_dump():
    """
    分析现有的 dump_ax_tree 输出格式
    看看是否包含快捷键信息
    """
    print("\n" + "=" * 70)
    print("分析现有 dump_ax_tree 输出")
    print("=" * 70)
    
    # 模拟一个 dump_ax_tree 的输出
    # 实际应该在代码中调用，但这里先用模拟数据说明
    sample_ax_output = [
        {
            "name": "文件",
            "role": "AXMenuBarItem",
            "path": "menu bar item 1 of menu bar 1",
            "bounds": [10, 10, 50, 20]
        },
        {
            "name": "新建标签页",
            "role": "AXMenuItem",
            "path": "menu item 1 of menu 1 of menu bar item 1",
            "bounds": [0, 0, 0, 0]
            # 注意：这里可能缺少快捷键信息
        }
    ]
    
    print("\n示例 AX Tree 元素:")
    for item in sample_ax_output:
        print(f"  - {item['name']} ({item['role']})")
        print(f"    Path: {item['path']}")
        if 'shortcut' in item:
            print(f"    Shortcut: {item['shortcut']}")
        else:
            print(f"    Shortcut: (未包含)")


def main():
    print("=" * 70)
    print("🔍 从 Accessibility Tree 提取快捷键信息测试")
    print("=" * 70)
    print("\n测试原理:")
    print("  macOS Accessibility API 理论上可以获取菜单项的快捷键信息")
    print("  包括: AXMenuItemCmdChar (快捷键字符) 和 AXMenuItemCmdModifiers (修饰键)")
    print()
    
    # 方法 1: AppleScript
    print("\n" + "=" * 70)
    print("方法 1: AppleScript 获取菜单快捷键")
    print("=" * 70)
    result = get_ax_tree_via_applescript()
    print(f"\n结果:\n{result}")
    
    # 方法 2: PyObjC (如果可用)
    print("\n" + "=" * 70)
    print("方法 2: PyObjC 直接调用 AX API")
    print("=" * 70)
    shortcuts = get_ax_tree_via_pyobjc()
    if shortcuts is not None:
        if shortcuts:
            print(f"\n找到 {len(shortcuts)} 个带快捷键的菜单项:")
            for s in shortcuts:
                print(f"  - {s['name']}: {s['shortcut']} (modifiers: {s['modifiers']})")
        else:
            print("\n未找到快捷键信息")
    
    # 分析现有输出
    analyze_existing_dump()
    
    # 测试不同应用
    test_specific_apps()
    
    print("\n" + "=" * 70)
    print("📋 结论")
    print("=" * 70)
    print("""
【测试结果分析】

1. AX API 确实支持获取菜单快捷键:
   - AXMenuItemCmdChar: 快捷键字符 (如 "N", "S")
   - AXMenuItemCmdModifiers: 修饰键 (如 Cmd=1, Shift=2, Option=4, Ctrl=8)

2. 但是获取有难度:
   - 需要遍历完整的菜单树
   - 不是所有应用都正确实现这些属性
   - 动态菜单项可能没有快捷键信息

3. 实际可行性:
   ✅ 技术可行: AX API 支持
   ⚠️ 实现复杂: 需要递归遍历所有菜单
   ❌ 覆盖不全: 动态/自定义快捷键可能获取不到

4. 建议方案:
   - 高频应用 (微信、Safari): 手动维护快捷键数据库
   - 低频应用: 实时遍历 AX Tree 获取
   - 混合策略: 数据库 + 动态获取 fallback
""")


if __name__ == "__main__":
    main()
