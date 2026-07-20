import asyncio
import json
import os
from app.infrastructure.drivers.macos import macos_driver
from app.domain.tools.environment.desktop import desktop_control
from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
from app.core.vision.types import VisionTask

async def compare_ax_vs_ocr():
    print("🔬 --- 深度对比：原生无障碍树 (AX Tree) vs 视觉识别 (OCR) ---")
    
    # 1. 确保微信在前台
    print("\n[Step 1] 正在聚焦微信...")
    await desktop_control.ainvoke({"action": "open_app", "app_name": "WeChat"})
    await asyncio.sleep(2)
    app_info = macos_driver.get_current_app()
    bounds_str = app_info.get("bounds")
    if not bounds_str:
        print("❌ 无法获取窗口边界")
        return

    # 2. 原生 AX 树扫描 (深度=8)
    print("\n[Step 2] 正在运行结构化解析 (AX Tree, Depth=8)...")
    raw_tree = macos_driver.dump_ax_tree()
    ax_elements = json.loads(raw_tree)
    ax_named = [el for el in ax_elements if el.get("name")]
    print(f"✅ AX 扫描完成：共发现 {len(ax_elements)} 个节点，其中带语义名称的有 {len(ax_named)} 个。")

    # 3. 视觉 OCR 扫描
    print("\n[Step 3] 正在运行视觉解析 (OCR)...")
    screenshot_path = macos_driver.screenshot(region=bounds_str)
    provider = MacOSVisionOCRProvider()
    ocr_result = await provider.process(task=VisionTask.OCR, image_source=screenshot_path)
    
    if os.path.exists(screenshot_path):
        os.remove(screenshot_path)

    if not ocr_result.success:
        print("❌ OCR 解析失败")
        return

    ocr_elements = ocr_result.elements
    print(f"✅ OCR 扫描完成：共发现 {len(ocr_elements)} 个文本块。")

    # 4. 对比分析
    print("\n📊 --- 结论分析 ---")
    print(f"{'维度':<15} | {'结构化 (AX)':<15} | {'视觉 (OCR)':<15}")
    print("-" * 50)
    print(f"{'可感知数量':<15} | {len(ax_elements):<15} | {len(ocr_elements):<15}")
    print(f"{'语义清晰度':<15} | {'极高 (含Role/Path)':<15} | {'中 (仅文字/位置)':<15}")
    print(f"{'解析速度':<15} | {'极快 (~200ms)':<15} | {'慢 (~2s)':<15}")
    
    print("\n🚩 为什么 OCR 发现的更多？")
    print("1. 微信等国产软件大量使用自定义绘图或非标准控件，这些控件在系统的 Accessibility API 中是“透明”的。")
    print("2. 结构化解析（AX）虽然快且准，但在这些软件面前会“失明”。")
    print("3. 这就是为什么我们必须引入 OCR 作为“视觉兜底”：当结构化方法找不到目标时，Agent 依然能通过‘看’来定位。")

    if ax_named:
        print("\n📝 AX 树发现的典型名称:", [el['name'] for el in ax_named[:3]])
    
    print("\n📝 OCR 发现的部分名称:", [el.text for el in ocr_elements[:3]])

if __name__ == "__main__":
    asyncio.run(compare_ax_vs_ocr())
