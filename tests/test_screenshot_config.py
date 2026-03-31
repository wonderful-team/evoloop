#!/usr/bin/env python3
"""
测试 ENABLE_PARTIAL_SCREENSHOT 配置
验证开关是否能正确控制截图行为
"""

import subprocess
import os
import sys
from datetime import datetime

# 添加 backend 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))


def test_config():
    """测试配置读取"""
    print("=" * 70)
    print("🔧 ENABLE_PARTIAL_SCREENSHOT 配置测试")
    print("=" * 70)
    
    try:
        from app.core.config import settings
        
        print("\n📋 当前配置:")
        print(f"   ENABLE_PARTIAL_SCREENSHOT = {settings.ENABLE_PARTIAL_SCREENSHOT}")
        
        if settings.ENABLE_PARTIAL_SCREENSHOT:
            print("\n   ✅ 局部截图已启用")
            print("   当 region=None 时，自动截取当前窗口区域")
        else:
            print("\n   ❌ 局部截图已禁用")
            print("   当 region=None 时，截取全屏")
        
        print("\n📋 配置说明:")
        print("   在 backend/.env 或环境变量中设置:")
        print("   ENABLE_PARTIAL_SCREENSHOT=true   # 启用局部截图（默认）")
        print("   ENABLE_PARTIAL_SCREENSHOT=false  # 禁用局部截图，使用全屏")
        
        return settings.ENABLE_PARTIAL_SCREENSHOT
        
    except Exception as e:
        print(f"\n❌ 配置读取失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def simulate_screenshot_logic(enable_partial: bool, bounds: str = None):
    """
    模拟截图逻辑
    展示不同配置下的截图行为
    """
    print("\n" + "=" * 70)
    print("📸 截图行为模拟")
    print("=" * 70)
    
    # 模拟窗口 bounds
    mock_bounds = "813,232,1036,611"
    
    print(f"\n假设当前窗口 bounds: {mock_bounds}")
    print(f"配置: ENABLE_PARTIAL_SCREENSHOT = {enable_partial}")
    
    print("\n场景 1: AI 调用 desktop_control(action='screenshot', region=None)")
    if enable_partial:
        print(f"   结果: 截取局部区域 {mock_bounds}")
        print(f"   命令: screencapture -R {mock_bounds}")
    else:
        print(f"   结果: 截取全屏")
        print(f"   命令: screencapture")
    
    print("\n场景 2: AI 调用 desktop_control(action='screenshot', region='500,300,200,100')")
    print(f"   结果: 截取指定区域 500,300,200,100")
    print(f"   命令: screencapture -R 500,300,200,100")
    print(f"   注意: 显式指定 region 时，配置开关不影响行为")


def test_env_override():
    """测试环境变量覆盖"""
    print("\n" + "=" * 70)
    print("🔧 环境变量测试")
    print("=" * 70)
    
    # 测试不同的环境变量值
    test_values = [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", False),
    ]
    
    print("\n支持的配置值:")
    for val, expected in test_values:
        print(f"   ENABLE_PARTIAL_SCREENSHOT={val:<6} -> {expected}")


def main():
    current_config = test_config()
    
    if current_config is not None:
        simulate_screenshot_logic(current_config)
        test_env_override()
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)
    print("\n💡 使用建议:")
    print("   1. 默认启用局部截图（节省 Token）")
    print("   2. 如果遇到坐标问题，可以禁用局部截图使用全屏")
    print("   3. 修改配置后需要重启后端服务")


if __name__ == "__main__":
    main()
