#!/usr/bin/env python3
"""
单独测试 Step 3 的 Vision LLM 检测
"""

import os
import sys
from pathlib import Path

os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

def load_env_file():
    env_path = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value

load_env_file()
sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")


async def main():
    from app.core.execution.macro.anomaly_detector import AnomalyDetector
    from app.core.execution.macro.verification_models import AnomalyType

    print("=" * 80)
    print("🔍 测试 Step 3 的 Vision LLM 检测")
    print("=" * 80)

    detector = AnomalyDetector()

    # Step 3: 点击"角色"
    step = {
        "type": "action",
        "event_type": "tap",
        "target_selector": "角色",
        "payload": {"x": 0.309, "y": 0.268}
    }

    # 执行前状态
    pre_state = {
        "elements": [{"text": "角色"}, {"text": "召唤兽"}]
    }

    # 使用已有的截图测试
    screenshot_path = "/Users/huangjinhuan/.evoloop/artifacts/screenshots/temp/20260313/android_20260313_081014_841.png"

    # 执行后状态 - 包含截图路径
    post_state = {
        "elements": [{"text": "充值中心"}, {"text": "50点"}],
        "screenshot": screenshot_path if Path(screenshot_path).exists() else None
    }

    print(f"\n步骤: 点击'角色'")
    print(f"截图存在: {Path(screenshot_path).exists()}")
    print(f"截图路径: {post_state['screenshot']}")
    print()

    # 先单独测试 Vision LLM 分析
    print("🧠 直接调用 Vision LLM 分析...")
    vision_result = await detector.analyze_with_vision_llm(screenshot_path, step)

    if vision_result:
        print(f"  Vision LLM 检测到异常: {vision_result.is_anomaly}")
        print(f"  类型: {vision_result.anomaly_type}")
        print(f"  置信度: {vision_result.confidence}")
        print(f"  问题: {vision_result.details.get('issue')}")
    else:
        print("  Vision LLM 返回 None (可能是分析失败)")

    # 再测试完整的执行后检测
    print("\n🔍 调用完整 detect_post_execution_anomaly...")
    result = await detector.detect_post_execution_anomaly(
        step, pre_state, post_state, "Tapped"
    )

    print(f"\n  检测结果:")
    print(f"    is_anomaly: {result.is_anomaly}")
    print(f"    type: {result.anomaly_type}")
    print(f"    confidence: {result.confidence}")
    print(f"    suggested_action: {result.suggested_action}")

    if result.details.get("vision_analysis"):
        print("\n    ✅ Vision LLM 分析被纳入检测结果!")
        print(f"    issue: {result.details.get('issue')}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
