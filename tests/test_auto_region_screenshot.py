#!/usr/bin/env python3
"""
测试脚本：自动获取当前窗口 bounds 并进行局部截图
不依赖 LLM，纯代码方式实现
"""

import asyncio
import sys
import os

# 添加 client 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'client'))

from app.infrastructure.drivers.macos import macos_driver


def test_get_current_window_bounds():
    """测试获取当前窗口的 bounds"""
    print("=" * 60)
    print("测试 1: 获取当前活动窗口信息")
    print("=" * 60)
    
    app_info = macos_driver.get_current_app()
    print(f"应用名称: {app_info.get('name')}")
    print(f"Bundle ID: {app_info.get('bundle_id')}")
    print(f"窗口标题: {app_info.get('title')}")
    print(f"窗口 Bounds: {app_info.get('bounds')}")
    
    return app_info


def test_full_screenshot():
    """测试全屏截图（对比用）"""
    print("\n" + "=" * 60)
    print("测试 2: 全屏截图")
    print("=" * 60)
    
    filepath = macos_driver.screenshot(region=None, purpose="temp")
    print(f"全屏截图保存路径: {filepath}")
    
    # 获取文件大小
    file_size = os.path.getsize(filepath)
    print(f"文件大小: {file_size / 1024:.2f} KB")
    
    # 获取图片尺寸
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            print(f"图片尺寸: {img.size[0]} x {img.size[1]} pixels")
    except ImportError:
        print("PIL 未安装，跳过尺寸检测")
    
    return filepath


def test_window_region_screenshot(app_info: dict):
    """测试使用窗口 bounds 进行局部截图"""
    print("\n" + "=" * 60)
    print("测试 3: 局部截图（基于窗口 bounds）")
    print("=" * 60)
    
    bounds = app_info.get('bounds')
    if not bounds:
        print("错误: 无法获取窗口 bounds")
        return None
    
    print(f"使用 bounds: {bounds}")
    
    try:
        filepath = macos_driver.screenshot(
            region=bounds,
            purpose="temp",
            bundle_id=app_info.get('bundle_id')
        )
        print(f"局部截图保存路径: {filepath}")
        
        # 获取文件大小
        file_size = os.path.getsize(filepath)
        print(f"文件大小: {file_size / 1024:.2f} KB")
        
        # 获取图片尺寸
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                print(f"图片尺寸: {img.size[0]} x {img.size[1]} pixels")
        except ImportError:
            print("PIL 未安装，跳过尺寸检测")
        
        return filepath
        
    except Exception as e:
        print(f"局部截图失败: {e}")
        return None


def test_region_with_offset(app_info: dict):
    """测试带有偏移的局部截图（模拟只截取窗口的一部分）"""
    print("\n" + "=" * 60)
    print("测试 4: 局部截图（带偏移 - 只截取窗口上半部分）")
    print("=" * 60)
    
    bounds = app_info.get('bounds')
    if not bounds:
        print("错误: 无法获取窗口 bounds")
        return None
    
    try:
        # 解析 bounds
        x, y, w, h = map(int, bounds.split(','))
        print(f"原始 bounds: x={x}, y={y}, w={w}, h={h}")
        
        # 只截取上半部分
        partial_h = h // 2
        region = f"{x},{y},{w},{partial_h}"
        print(f"截取区域: {region} (上半部分)")
        
        filepath = macos_driver.screenshot(
            region=region,
            purpose="temp",
            bundle_id=app_info.get('bundle_id')
        )
        print(f"局部截图保存路径: {filepath}")
        
        # 获取文件大小
        file_size = os.path.getsize(filepath)
        print(f"文件大小: {file_size / 1024:.2f} KB")
        
        # 获取图片尺寸
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                print(f"图片尺寸: {img.size[0]} x {img.size[1]} pixels")
        except ImportError:
            pass
        
        return filepath
        
    except Exception as e:
        print(f"局部截图失败: {e}")
        return None


async def test_desktop_controller_auto_region():
    """测试 DesktopController 的自动区域截图功能"""
    print("\n" + "=" * 60)
    print("测试 5: 通过 DesktopController 自动获取 bounds 并截图")
    print("=" * 60)
    
    try:
        from app.core.environment.controllers.desktop_controller import DesktopController
        
        # 先获取当前应用信息
        app_info = macos_driver.get_current_app()
        bounds = app_info.get('bounds')
        
        print(f"当前应用: {app_info.get('name')}")
        print(f"窗口 bounds: {bounds}")
        
        # 使用 bounds 进行局部截图
        if bounds:
            result = await DesktopController.execute(
                action="screenshot",
                region=bounds,
                ocr=False
            )
            print(f"截图结果:\n{result}")
        else:
            print("无法获取 bounds，跳过测试")
            
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


def compare_file_sizes(full_path: str, region_path: str):
    """对比全屏和局部截图的文件大小"""
    print("\n" + "=" * 60)
    print("对比: 全屏 vs 局部截图")
    print("=" * 60)
    
    if not os.path.exists(full_path):
        print(f"全屏截图文件不存在: {full_path}")
        return
    if not os.path.exists(region_path):
        print(f"局部截图文件不存在: {region_path}")
        return
    
    full_size = os.path.getsize(full_path)
    region_size = os.path.getsize(region_path)
    
    print(f"全屏截图: {full_size / 1024:.2f} KB")
    print(f"局部截图: {region_size / 1024:.2f} KB")
    
    if full_size > 0:
        reduction = (1 - region_size / full_size) * 100
        print(f"节省空间: {reduction:.1f}%")


async def main():
    """主测试函数"""
    print("🧪 macOS 自动局部截图测试")
    print("请确保当前有一个活动窗口（如 Safari、微信等）")
    print("3 秒后开始测试...")
    await asyncio.sleep(3)
    
    # 测试 1: 获取窗口信息
    app_info = test_get_current_window_bounds()
    
    if not app_info.get('bounds'):
        print("\n❌ 无法获取窗口 bounds，测试中止")
        print("请确保已授权辅助功能权限")
        return
    
    # 测试 2: 全屏截图
    full_path = test_full_screenshot()
    
    # 测试 3: 窗口区域截图
    region_path = test_window_region_screenshot(app_info)
    
    # 测试 4: 带偏移的局部截图
    partial_path = test_region_with_offset(app_info)
    
    # 测试 5: DesktopController 方式
    await test_desktop_controller_auto_region()
    
    # 对比结果
    if full_path and region_path:
        compare_file_sizes(full_path, region_path)
    
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)
    print("\n总结:")
    print("- 使用 macos_driver.get_current_app() 可以自动获取窗口 bounds")
    print("- 使用 macos_driver.screenshot(region=bounds) 可以进行局部截图")
    print("- 局部截图文件大小通常比全屏截图小 30-70%")
    print("- 这种方式完全不需要 LLM 参与，纯代码实现")


if __name__ == "__main__":
    asyncio.run(main())
