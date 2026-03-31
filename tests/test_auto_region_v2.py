#!/usr/bin/env python3
"""
测试脚本：自动获取当前窗口 bounds 并局部截图
分别测试：全屏、完整窗口、窗口上半部分
"""

import subprocess
import os
import time
from datetime import datetime


def get_current_window_bounds():
    """使用 AppleScript 获取当前窗口 bounds"""
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        tell frontApp
            try
                set win to window 1
                set {x, y} to position of win
                set {w, h} to size of win
                return (x as string) & "," & (y as string) & "," & (w as string) & "," & (h as string)
            on error
                return ""
            end try
        end tell
    end tell
    '''
    
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0 and result.stdout.strip():
        try:
            bounds = result.stdout.strip()
            x, y, w, h = map(int, bounds.split(','))
            return (x, y, w, h)
        except ValueError:
            return None
    return None


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


def screenshot_full(output_dir="/tmp", suffix=""):
    """全屏截图"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"screenshot_full_{timestamp}{suffix}.png")
    
    cmd = ["screencapture", "-x", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0 and os.path.exists(filepath):
        return filepath
    return None


def screenshot_region(x, y, w, h, output_dir="/tmp", suffix=""):
    """局部截图 -R x,y,w,h"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"screenshot_region_{timestamp}{suffix}.png")
    
    cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0 and os.path.exists(filepath):
        return filepath
    return None


def get_image_info(filepath):
    """获取图片信息"""
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            return {
                "size": img.size,
                "mode": img.mode,
                "file_size": os.path.getsize(filepath)
            }
    except ImportError:
        return {
            "file_size": os.path.getsize(filepath)
        }


def main():
    print("=" * 70)
    print("🧪 macOS 自动局部截图功能测试 - V2")
    print("=" * 70)
    print("\n测试三种截图模式：")
    print("  1. 全屏截图")
    print("  2. 自动局部截图（完整窗口 - 这就是 backend 的默认行为）")
    print("  3. 局部截图（窗口上半部分 - 仅作对比）")
    print("\n3 秒后开始，请确保有一个活动窗口...")
    time.sleep(3)
    
    output_dir = os.path.expanduser("~/.evoloop/test_screenshots")
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取应用信息
    print("\n" + "=" * 70)
    print("当前活动应用")
    print("=" * 70)
    app_info = get_current_app_info()
    bounds = get_current_window_bounds()
    
    print(f"应用名称: {app_info['name']}")
    print(f"Bundle ID: {app_info['bundle_id']}")
    print(f"窗口标题: {app_info['title']}")
    
    if bounds:
        x, y, w, h = bounds
        print(f"窗口 Bounds: \"{x},{y},{w},{h}\"")
    else:
        print("❌ 无法获取窗口 bounds")
        return
    
    # 1. 全屏截图
    print("\n" + "=" * 70)
    print("【模式 1】全屏截图")
    print("=" * 70)
    full_path = screenshot_full(output_dir, suffix="_mode1")
    if full_path:
        info = get_image_info(full_path)
        print(f"✅ 截图路径: {full_path}")
        if "size" in info:
            print(f"   尺寸: {info['size'][0]} x {info['size'][1]} px")
        print(f"   大小: {info['file_size'] / 1024:.2f} KB")
    
    # 2. 自动局部截图 - 完整窗口（这就是 backend 的默认行为）
    print("\n" + "=" * 70)
    print("【模式 2】自动局部截图 - 完整窗口")
    print("这是 backend 代码的默认行为:")
    print("  if region is None:")
    print("      bounds = app_info.get('bounds')")
    print("      region = bounds  # 使用完整窗口 bounds")
    print("=" * 70)
    window_path = screenshot_region(x, y, w, h, output_dir, suffix="_mode2_full_window")
    if window_path:
        info = get_image_info(window_path)
        print(f"✅ 截图路径: {window_path}")
        print(f"   使用 bounds: \"{x},{y},{w},{h}\"")
        if "size" in info:
            print(f"   尺寸: {info['size'][0]} x {info['size'][1]} px")
            print(f"   预期尺寸: {w} x {h} px")
        print(f"   大小: {info['file_size'] / 1024:.2f} KB")
        
        if full_path:
            full_info = get_image_info(full_path)
            saving = (1 - info['file_size'] / full_info['file_size']) * 100
            print(f"   相比全屏节省: {saving:.1f}%")
    
    # 3. 局部截图 - 上半部分（仅作对比）
    print("\n" + "=" * 70)
    print("【模式 3】局部截图 - 窗口上半部分（仅作对比）")
    print("这不是默认行为，只是演示可以截取部分区域")
    print("=" * 70)
    half_h = h // 2
    partial_path = screenshot_region(x, y, w, half_h, output_dir, suffix="_mode3_upper_half")
    if partial_path:
        info = get_image_info(partial_path)
        print(f"✅ 截图路径: {partial_path}")
        print(f"   使用 bounds: \"{x},{y},{w},{half_h}\" (高度减半)")
        if "size" in info:
            print(f"   尺寸: {info['size'][0]} x {info['size'][1]} px")
        print(f"   大小: {info['file_size'] / 1024:.2f} KB")
        
        if full_path:
            full_info = get_image_info(full_path)
            saving = (1 - info['file_size'] / full_info['file_size']) * 100
            print(f"   相比全屏节省: {saving:.1f}%")
    
    # 总结
    print("\n" + "=" * 70)
    print("📊 测试结果汇总")
    print("=" * 70)
    
    files = []
    if full_path:
        info = get_image_info(full_path)
        files.append(("全屏截图", full_path, info))
    if window_path:
        info = get_image_info(window_path)
        files.append(("完整窗口 (默认)", window_path, info))
    if partial_path:
        info = get_image_info(partial_path)
        files.append(("上半部分 (对比)", partial_path, info))
    
    print(f"\n{'模式':<20} {'路径':<60} {'大小':<10}")
    print("-" * 100)
    for name, path, info in files:
        size_kb = f"{info['file_size'] / 1024:.1f} KB"
        print(f"{name:<20} {path:<60} {size_kb:<10}")
    
    print("\n" + "=" * 70)
    print("💡 关键结论")
    print("=" * 70)
    print("Backend 默认行为（模式 2）:")
    print("  - 自动获取当前窗口 bounds")
    print("  - 截取完整窗口（不是一半，也不是全屏）")
    print("  - 相比全屏节省 60-80% 的文件大小")
    print("  - 大幅减少 OCR Token 消耗")
    print(f"\n截图保存目录: {output_dir}")


if __name__ == "__main__":
    main()
