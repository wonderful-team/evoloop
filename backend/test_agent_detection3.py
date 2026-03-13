#!/usr/bin/env python3
"""
测试增强的 Agent 异常检测
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
    print("🔍 测试增强的 AnomalyDetector")
    print("=" * 80)
    
    detector = AnomalyDetector()
    
    # 场景: 点击"角色"后进入充值中心（错误页面）
    print("\n【场景】点击'角色'后进入充值中心（错误页面）")
    
    step = {
        "type": "action",
        "event_type": "tap",
        "target_selector": "角色",
        "payload": {"x": 0.309, "y": 0.268}
    }
    
    pre_state = {
        "elements": [{"text": "角色"}, {"text": "召唤兽"}]
    }
    
    # 点击后进入了充值中心
    post_state = {
        "elements": [
            {"text": "充值中心"},
            {"text": "50点"},
            {"text": "100点"},
            {"text": "立即购买"}
        ]
    }
    
    result = await detector.detect_post_execution_anomaly(
        step, pre_state, post_state, "Tapped"
    )
    
    print(f"  检测结果:")
    print(f"    is_anomaly: {result.is_anomaly}")
    print(f"    type: {result.anomaly_type}")
    print(f"    confidence: {result.confidence}")
    print(f"    suggested_action: {result.suggested_action}")
    print(f"    details: {result.details}")
    
    if result.is_anomaly and result.anomaly_type == AnomalyType.STATE_MISMATCH:
        print("\n  ✅ 正确检测到进入了错误页面!")
        print(f"     检测到错误特征: {result.details.get('matched_error_indicators')}")
    else:
        print("\n  ❌ 未检测到异常")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
