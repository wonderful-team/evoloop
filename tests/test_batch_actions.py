#!/usr/bin/env python3
"""
测试 Batch 多步操作功能
演示如何在一个焦点中完成：点击 -> 输入 -> 回车
"""

import subprocess
import os
import time
import sys
from datetime import datetime


def get_current_app_info():
    """获取当前应用信息"""
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        set appName to name of frontApp
        set bundleId to bundle identifier of frontApp
        try
            set winTitle to name of window 1 of frontApp
        on error
            set winTitle to ""
        end try
        return appName & "::" & bundleId & "::" & winTitle
    end tell
    '''
    
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0:
        parts = result.stdout.strip().split("::")
        return {
            "name": parts[0] if len(parts) > 0 else "Unknown",
            "bundle_id": parts[1] if len(parts) > 1 else "",
            "title": parts[2] if len(parts) > 2 else ""
        }
    return {"name": "Unknown", "bundle_id": "", "title": ""}


def click_at(x, y):
    """在指定坐标点击"""
    script = f'''
    tell application "System Events"
        click at {{{x}, {y}}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    return result.returncode == 0


def type_text(text):
    """输入文本"""
    escaped = text.replace('"', '\\"')
    script = f'''
    tell application "System Events"
        keystroke "{escaped}"
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    return result.returncode == 0


def key_press(key):
    """按键"""
    key_map = {
        "return": "return",
        "enter": "return",
        "escape": "escape",
        "tab": "tab",
    }
    key_code = key_map.get(key.lower(), key)
    
    script = f'''
    tell application "System Events"
        key code 36  -- return key
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    return result.returncode == 0


def execute_batch_workflow(actions, delay_ms=300):
    """
    执行批量操作工作流
    
    Args:
        actions: 动作列表，每个动作是 {"action": str, ...params}
        delay_ms: 动作间延迟（毫秒）
    """
    print(f"\n执行批量工作流 ({len(actions)} 个动作):")
    print("-" * 60)
    
    results = []
    for i, action_dict in enumerate(actions, 1):
        action = action_dict.get("action")
        params = {k: v for k, v in action_dict.items() if k != "action"}
        
        print(f"  [{i}/{len(actions)}] {action} {params} ... ", end="", flush=True)
        
        try:
            if action == "click":
                x = params.get("x", 0)
                y = params.get("y", 0)
                success = click_at(x, y)
                
            elif action == "type_text":
                text = params.get("text", "")
                success = type_text(text)
                
            elif action == "key_press":
                key = params.get("key", "")
                success = key_press(key)
                
            else:
                print(f"❌ 未知动作: {action}")
                results.append({"step": i, "action": action, "status": "error", "error": "Unknown action"})
                continue
            
            if success:
                print("✅")
                results.append({"step": i, "action": action, "status": "success"})
            else:
                print("❌")
                results.append({"step": i, "action": action, "status": "error"})
                
        except Exception as e:
            print(f"❌ {e}")
            results.append({"step": i, "action": action, "status": "error", "error": str(e)})
        
        # 动作间延迟
        if i < len(actions) and delay_ms > 0:
            time.sleep(delay_ms / 1000)
    
    print("-" * 60)
    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"结果: {success_count}/{len(actions)} 成功")
    
    return results


def main():
    print("=" * 70)
    print("🚀 Batch 多步操作测试")
    print("=" * 70)
    print("\n这个测试演示如何在一个焦点中完成多步操作")
    print("例如：点击输入框 -> 输入内容 -> 回车发送")
    print("\n请确保当前有一个可以输入的应用（如微信、备忘录等）")
    print("5 秒后开始...")
    time.sleep(5)
    
    # 获取当前应用信息
    app_info = get_current_app_info()
    print(f"\n📱 当前应用: {app_info['name']}")
    print(f"   窗口标题: {app_info['title']}")
    
    # 定义多步工作流
    # 示例：在微信中发送消息
    workflow = [
        # 步骤 1: 点击输入框（假设坐标）
        {"action": "click", "x": 1200, "y": 750, "description": "点击输入框"},
        
        # 步骤 2: 输入文本
        {"action": "type_text", "text": "这是一条测试消息", "description": "输入消息"},
        
        # 步骤 3: 回车发送
        {"action": "key_press", "key": "return", "description": "发送消息"},
    ]
    
    print("\n" + "=" * 70)
    print("📋 工作流定义")
    print("=" * 70)
    
    for i, step in enumerate(workflow, 1):
        desc = step.pop("description", "")
        print(f"  {i}. {desc}: {step}")
        step["description"] = desc  # 恢复
    
    # 执行工作流
    print("\n" + "=" * 70)
    print("▶️  执行工作流")
    print("=" * 70)
    
    results = execute_batch_workflow(workflow, delay_ms=500)
    
    # 对比：传统方式（每步截图验证）
    print("\n" + "=" * 70)
    print("📊 对比：传统方式 vs Batch 方式")
    print("=" * 70)
    
    print("""
传统方式（逐步验证）:
  1. screenshot + OCR → 找到输入框坐标
  2. click(x, y)
  3. screenshot + OCR → 确认点击成功
  4. type_text("...")
  5. screenshot + OCR → 确认文本已输入
  6. key_press("return")
  7. screenshot → 确认发送成功
  
  总共: 4 次截图, 3 次 OCR, 7 次 API 调用

Batch 方式（多步操作）:
  1. screenshot + OCR → 找到输入框坐标
  2. batch([
       {"action": "click", ...},
       {"action": "type_text", ...},
       {"action": "key_press", ...}
     ])
  3. screenshot → 确认结果
  
  总共: 2 次截图, 1 次 OCR, 2 次 API 调用

优势:
  ✅ 减少 50-70% 的截图和 OCR 调用
  ✅ 减少 Token 消耗
  ✅ 操作更连贯，减少延迟
  ✅ 适合确定的、连续的操作流程
""")
    
    print("=" * 70)
    print("✅ 测试完成")
    print("=" * 70)
    
    print("\n💡 在 Backend 中使用:")
    print("""
  # AI 调用示例:
  desktop_control(
      action="batch",
      actions=[
          {"action": "click", "element_name": "输入框"},
          {"action": "type_text", "text": "Hello World"},
          {"action": "key_press", "key": "return"}
      ],
      delay_ms=300
  )
""")


if __name__ == "__main__":
    main()
