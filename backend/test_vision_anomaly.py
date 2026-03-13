#!/usr/bin/env python3
"""
测试 Vision LLM 异常检测
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
    
    print("=" * 80)
    print("🔍 测试 Vision LLM 异常检测")
    print("=" * 80)
    
    detector = AnomalyDetector()
    
    # 模拟点击"角色"后的状态
    step = {
        "type": "action",
        "event_type": "tap",
        "target_selector": "角色",
        "payload": {"x": 0.309, "y": 0.268}
    }
    
    pre_state = {"elements": [{"text": "角色"}]}
    
    # 使用一张实际截图测试
    screenshot_path = "/Users/huangjinhuan/.evoloop/artifacts/screenshots/temp/20260313/android_20260313_081014_841.png"
    
    post_state = {
        "elements": [{"text": "充值中心"}],
        "screenshot": screenshot_path if Path(screenshot_path).exists() else None
    }
    
    print(f"\n步骤: 点击'角色'")
    print(f"截图: {post_state['screenshot']}")
    print()
    
    result = await detector.detect_post_execution_anomaly(
        step, pre_state, post_state, "Tapped"
    )
    
    print("检测结果:")
    print(f"  is_anomaly: {result.is_anomaly}")
    print(f"  type: {result.anomaly_type}")
    print(f"  confidence: {result.confidence}")
    print(f"  suggested_action: {result.suggested_action}")
    print(f"  details: {result.details}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
