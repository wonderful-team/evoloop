#!/usr/bin/env python3
"""
真实 OCR 测试 - 使用 macOS Vision API
"""

import subprocess
import os
import sys
from datetime import datetime

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'client'))


def get_window_bounds():
    """获取窗口 bounds"""
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
    
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    if result.returncode == 0 and result.stdout.strip():
        try:
            x, y, w, h = map(int, result.stdout.strip().split(','))
            return (x, y, w, h)
        except:
            pass
    return None


def screenshot_region(x, y, w, h, output_path):
    """局部截图"""
    cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return result.returncode == 0 and os.path.exists(output_path)


def run_ocr(image_path):
    """运行 OCR"""
    try:
        from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
        from app.core.vision import VisionTask
        
        provider = MacOSVisionOCRProvider()
        result = provider.process(VisionTask.OCR, image_path)
        
        if result.success and result.elements:
            return result.elements
        return []
    except Exception as e:
        print(f"OCR 错误: {e}")
        return []


def main():
    print("=" * 70)
    print("🔍 真实 OCR 坐标转换测试")
    print("=" * 70)
    print("\n5 秒后开始，请确保有一个活动窗口（如微信、Safari）...")
    import time
    time.sleep(5)
    
    output_dir = os.path.expanduser("~/.evoloop/test_screenshots")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 获取 bounds
    bounds = get_window_bounds()
    if not bounds:
        print("❌ 无法获取窗口 bounds")
        return
    
    wx, wy, ww, wh = bounds
    print(f"\n📍 窗口 Bounds: {wx},{wy},{ww},{wh}")
    
    # 截图 1: 全屏（对比）
    print("\n" + "-" * 70)
    print("【截图 1】全屏截图 + OCR")
    print("-" * 70)
    
    full_path = os.path.join(output_dir, f"real_ocr_full_{timestamp}.png")
    subprocess.run(["screencapture", "-x", full_path], timeout=10)
    
    if os.path.exists(full_path):
        print(f"✅ 全屏截图: {full_path}")
        elements_full = run_ocr(full_path)
        print(f"   OCR 检测到 {len(elements_full)} 个元素")
        
        if elements_full:
            print("   前 3 个元素（坐标已经是屏幕坐标）:")
            for i, el in enumerate(elements_full[:3]):
                print(f"   [{i}] '{el.text[:20]}...' at ({el.x}, {el.y})")
    
    # 截图 2: 局部
    print("\n" + "-" * 70)
    print("【截图 2】局部截图 + OCR（坐标已转换）")
    print("-" * 70)
    
    region_path = os.path.join(output_dir, f"real_ocr_region_{timestamp}.png")
    if screenshot_region(wx, wy, ww, wh, region_path):
        print(f"✅ 局部截图: {region_path}")
        print(f"   截图区域: ({wx}, {wy}) 到 ({wx+ww}, {wy+wh})")
        
        elements_region = run_ocr(region_path)
        print(f"   OCR 检测到 {len(elements_region)} 个元素")
        
        if elements_region:
            print("\n   OCR 原始结果（相对坐标）:")
            for i, el in enumerate(elements_region[:3]):
                print(f"   [{i}] '{el.text[:20]}...' at ({el.x}, {el.y}) [相对]")
            
            print(f"\n   应用坐标转换（backend 逻辑）:")
            print(f"   region_offset = ({wx}, {wy})")
            
            print("\n   转换后结果（屏幕坐标）:")
            for i, el in enumerate(elements_region[:3]):
                screen_x = el.x + wx
                screen_y = el.y + wy
                print(f"   [{i}] '{el.text[:20]}...' at ({screen_x}, {screen_y}) [屏幕]")
                
                # 验证
                in_bounds = (wx <= screen_x <= wx + ww) and (wy <= screen_y <= wy + wh)
                print(f"       验证: 相对({el.x}, {el.y}) + 偏移({wx}, {wy}) = 屏幕({screen_x}, {screen_y}) {'✅' if in_bounds else '❌'}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)
    print(f"\n截图保存目录: {output_dir}")


if __name__ == "__main__":
    main()
