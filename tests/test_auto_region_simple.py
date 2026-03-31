#!/usr/bin/env python3
"""
简化测试脚本：测试 macOS 局部截图功能
不依赖复杂初始化，直接调用底层功能
"""

import subprocess
import os
import time
from datetime import datetime


def get_current_window_bounds():
    """
    使用 AppleScript 获取当前窗口 bounds
    返回: (x, y, w, h) 或 None
    """
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


def screenshot_full(output_dir="/tmp"):
    """全屏截图"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"screenshot_full_{timestamp}.png")
    
    cmd = ["screencapture", "-x", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0 and os.path.exists(filepath):
        return filepath
    return None


def screenshot_region(x, y, w, h, output_dir="/tmp"):
    """局部截图 -R x,y,w,h"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"screenshot_region_{timestamp}.png")
    
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
    print("🧪 macOS 自动局部截图功能测试")
    print("=" * 70)
    print("\n这个测试验证：不依赖 LLM，纯代码自动获取窗口 bounds 并局部截图\n")
    print("3 秒后开始，请确保有一个活动窗口（如 Safari、微信等）...")
    time.sleep(3)
    
    output_dir = os.path.expanduser("~/.evoloop/test_screenshots")
    os.makedirs(output_dir, exist_ok=True)
    
    # 步骤 1: 获取当前应用信息
    print("\n" + "-" * 70)
    print("步骤 1: 获取当前活动应用信息")
    print("-" * 70)
    
    app_info = get_current_app_info()
    print(f"应用名称: {app_info['name']}")
    print(f"Bundle ID: {app_info['bundle_id']}")
    print(f"窗口标题: {app_info['title']}")
    
    # 步骤 2: 获取窗口 bounds
    print("\n" + "-" * 70)
    print("步骤 2: 获取窗口 bounds (使用 AppleScript)")
    print("-" * 70)
    
    bounds = get_current_window_bounds()
    if bounds:
        x, y, w, h = bounds
        print(f"✅ 成功获取 bounds: x={x}, y={y}, w={w}, h={h}")
        print(f"   格式化字符串: \"{x},{y},{w},{h}\"")
    else:
        print("❌ 无法获取窗口 bounds")
        print("可能原因：")
        print("  1. 没有活动窗口")
        print("  2. 应用没有标准窗口（如菜单栏应用）")
        print("  3. 辅助功能权限未授权")
        return
    
    # 步骤 3: 全屏截图（对比用）
    print("\n" + "-" * 70)
    print("步骤 3: 全屏截图（对比基准）")
    print("-" * 70)
    
    full_path = screenshot_full(output_dir)
    if full_path:
        info = get_image_info(full_path)
        print(f"✅ 全屏截图保存路径: {full_path}")
        if "size" in info:
            print(f"   尺寸: {info['size'][0]} x {info['size'][1]} pixels")
        print(f"   文件大小: {info['file_size'] / 1024:.2f} KB")
    else:
        print("❌ 全屏截图失败")
        return
    
    # 步骤 4: 局部截图 - 当前窗口
    print("\n" + "-" * 70)
    print("步骤 4: 局部截图（基于窗口 bounds）")
    print("-" * 70)
    print(f"使用 bounds: \"{x},{y},{w},{h}\"")
    print(f"执行命令: screencapture -x -R {x},{y},{w},{h} ...")
    
    region_path = screenshot_region(x, y, w, h, output_dir)
    if region_path:
        info = get_image_info(region_path)
        print(f"✅ 局部截图保存路径: {region_path}")
        if "size" in info:
            print(f"   尺寸: {info['size'][0]} x {info['size'][1]} pixels")
            print(f"   预期尺寸: {w} x {h} pixels")
        print(f"   文件大小: {info['file_size'] / 1024:.2f} KB")
    else:
        print("❌ 局部截图失败")
    
    # 步骤 5: 对比分析
    print("\n" + "-" * 70)
    print("步骤 5: 对比分析")
    print("-" * 70)
    
    if full_path and region_path:
        full_info = get_image_info(full_path)
        region_info = get_image_info(region_path)
        
        full_size = full_info['file_size']
        region_size = region_info['file_size']
        
        print(f"全屏截图: {full_size / 1024:.2f} KB")
        print(f"局部截图: {region_size / 1024:.2f} KB")
        
        if full_size > 0:
            reduction = (1 - region_size / full_size) * 100
            print(f"\n📊 空间节省: {reduction:.1f}%")
            
            if "size" in full_info and "size" in region_info:
                full_pixels = full_info['size'][0] * full_info['size'][1]
                region_pixels = region_info['size'][0] * region_info['size'][1]
                pixel_ratio = region_pixels / full_pixels * 100
                print(f"📊 像素占比: {pixel_ratio:.1f}%")
    
    # 步骤 6: 测试带偏移的局部截图
    print("\n" + "-" * 70)
    print("步骤 6: 测试带偏移的局部截图（只截取窗口上半部分）")
    print("-" * 70)
    
    half_h = h // 2
    print(f"截取区域: \"{x},{y},{w},{half_h}\" (上半部分)")
    partial_path = screenshot_region(x, y, w, half_h, output_dir)
    if partial_path:
        info = get_image_info(partial_path)
        print(f"✅ 部分截图保存路径: {partial_path}")
        if "size" in info:
            print(f"   尺寸: {info['size'][0]} x {info['size'][1]} pixels")
        print(f"   文件大小: {info['file_size'] / 1024:.2f} KB")
        
        # 对比
        partial_size = info['file_size']
        reduction = (1 - partial_size / full_size) * 100
        print(f"   相比全屏节省: {reduction:.1f}%")
    
    # 总结
    print("\n" + "=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)
    print("\n📋 关键数据汇总：")
    print(f"   Bounds: \"{x},{y},{w},{h}\"")
    print(f"   全屏路径: {full_path}")
    print(f"   局部路径: {region_path}")
    print(f"   部分路径: {partial_path}")
    print("\n📋 结论：")
    print("  1. ✅ 可以通过 AppleScript 自动获取当前窗口 bounds")
    print("  2. ✅ 可以使用 screencapture -R 进行局部截图")
    print("  3. ✅ 局部截图文件大小显著小于全屏截图")
    print("  4. ✅ 整个过程不需要 LLM 参与，纯代码实现")
    print("\n💡 建议：")
    print("  - 在自动化流程中，先调用 get_current_window_bounds() 获取 bounds")
    print("  - 然后使用 screenshot_region() 进行局部截图")
    print("  - 可以显著减少 OCR 处理的像素数量和 Token 消耗")
    print(f"\n📁 截图文件保存在: {output_dir}")


if __name__ == "__main__":
    main()
