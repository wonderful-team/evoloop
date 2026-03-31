#!/usr/bin/env python3
"""
测试 OCR 坐标系：局部截图 vs 全屏截图的坐标差异
"""

import subprocess
import os
import time
from datetime import datetime


def get_current_window_bounds():
    """获取当前窗口 bounds"""
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


def screenshot_region(x, y, w, h, output_path):
    """局部截图"""
    cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return result.returncode == 0 and os.path.exists(output_path)


def ocr_with_vision(filepath):
    """使用 macOS Vision API 进行 OCR"""
    script = f'''
import sys
sys.path.insert(0, 'client')

from PIL import Image
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision import VisionTask

provider = MacOSVisionOCRProvider()
result = provider.process(VisionTask.OCR, "{filepath}")

if result.success and result.elements:
    print("OCR Results:")
    for i, el in enumerate(result.elements[:5]):  # 只显示前5个
        print(f"  [{i}] Text: '{{el.text}}' | Coords: ({{el.x}}, {{el.y}})")
else:
    print("OCR failed or no text found")
'''
    # 保存临时脚本并执行
    temp_script = "/tmp/ocr_test.py"
    with open(temp_script, "w") as f:
        f.write(script)
    
    result = subprocess.run(
        ["python", temp_script],
        capture_output=True,
        text=True,
        timeout=30
    )
    return result.stdout, result.stderr


def simple_ocr_analysis(filepath):
    """简化版 OCR 分析，使用 PIL 找出图片中的文字区域"""
    try:
        from PIL import Image
        import numpy as np
        
        with Image.open(filepath) as img:
            # 简单的图像分析：找出非黑色区域（近似文字区域）
            # 这不是真正的 OCR，只是用来演示坐标系
            width, height = img.size
            
            print(f"  图片尺寸: {width} x {height}")
            print(f"  坐标系原点: (0, 0) - 图片左上角")
            print(f"  坐标系范围: (0, 0) 到 ({width}, {height})")
            
            return width, height
    except ImportError:
        print("  PIL 未安装，跳过图像分析")
        return None, None


def main():
    print("=" * 70)
    print("🔍 OCR 坐标系测试：局部截图 vs 全屏截图")
    print("=" * 70)
    print("\n关键问题：局部截图时，OCR 返回的坐标是相对于截图还是屏幕？")
    print("3 秒后开始...")
    time.sleep(3)
    
    output_dir = os.path.expanduser("~/.evoloop/test_screenshots")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 获取窗口 bounds
    bounds = get_current_window_bounds()
    if not bounds:
        print("❌ 无法获取窗口 bounds")
        return
    
    wx, wy, ww, wh = bounds
    print(f"\n📍 窗口 Bounds (屏幕坐标系):")
    print(f"   左上角: ({wx}, {wy})")
    print(f"   尺寸: {ww} x {wh}")
    print(f"   右下角: ({wx + ww}, {wy + wh})")
    
    # 1. 截取完整窗口
    print("\n" + "=" * 70)
    print("【测试 1】完整窗口局部截图")
    print("=" * 70)
    window_path = os.path.join(output_dir, f"ocr_test_window_{timestamp}.png")
    
    if screenshot_region(wx, wy, ww, wh, window_path):
        print(f"✅ 截图保存: {window_path}")
        print(f"   截图区域 (屏幕坐标): ({wx}, {wy}) 到 ({wx + ww}, {wy + wh})")
        print("\n   OCR 坐标系说明:")
        print(f"   - 截图内的坐标原点是截图左上角: ({wx}, {wy})")
        print(f"   - 截图内某点 (x, y) 对应的屏幕坐标是: ({wx} + x, {wy} + y)")
        print(f"   - 例如：截图内坐标 (100, 50) → 屏幕坐标 ({wx + 100}, {wy + 50})")
        
        # 获取图片尺寸
        w, h = simple_ocr_analysis(window_path)
        
        print(f"\n   坐标转换示例:")
        print(f"   假设 OCR 检测到按钮在截图内坐标 (100, 100):")
        print(f"   - 相对坐标 (截图内): (100, 100)")
        print(f"   - 绝对坐标 (屏幕上): ({wx} + 100, {wy} + 100) = ({wx + 100}, {wy + 100})")
    
    # 2. 对比：全屏截图
    print("\n" + "=" * 70)
    print("【测试 2】全屏截图（对比）")
    print("=" * 70)
    full_path = os.path.join(output_dir, f"ocr_test_full_{timestamp}.png")
    
    cmd = ["screencapture", "-x", full_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0 and os.path.exists(full_path):
        print(f"✅ 截图保存: {full_path}")
        print("\n   OCR 坐标系说明:")
        print("   - 截图内的坐标原点就是屏幕左上角: (0, 0)")
        print("   - 截图内某点 (x, y) 就是屏幕坐标 (x, y)")
        print("   - 不需要转换!")
        
        simple_ocr_analysis(full_path)
    
    # 3. 关键结论
    print("\n" + "=" * 70)
    print("📋 关键结论")
    print("=" * 70)
    
    print("""
【OCR 坐标系对比】

┌─────────────────────────────────────────────────────────────────────┐
│ 截图类型      │ 坐标系原点              │ 是否需要转换               │
├─────────────────────────────────────────────────────────────────────┤
│ 全屏截图      │ 屏幕左上角 (0, 0)       │ ❌ 不需要                  │
│ 局部截图      │ 截图区域左上角          │ ✅ 需要转换                │
└─────────────────────────────────────────────────────────────────────┘

【坐标转换公式】

局部截图时：
  屏幕_x = 截图区域_x + OCR检测_x
  屏幕_y = 截图区域_y + OCR检测_y

示例：
  窗口 bounds: "848,437,1036,611"
  OCR 检测到文字在截图内坐标: (100, 200)
  
  屏幕坐标 = (848 + 100, 437 + 200) = (948, 637)

【Backend 代码注意事项】

如果 backend 使用局部截图 + OCR，需要确保：

1. 截图时记录 bounds:
   bounds = app_info.get("bounds")  # "848,437,1036,611"
   screenshot(region=bounds)

2. OCR 后转换坐标:
   for element in ocr_result.elements:
       screen_x = bounds_x + element.x
       screen_y = bounds_y + element.y
       # 使用 screen_x, screen_y 进行点击

3. 如果直接使用 OCR 返回的坐标点击，会点到错误位置！
""")
    
    print(f"\n📁 测试截图保存在: {output_dir}")


if __name__ == "__main__":
    main()
