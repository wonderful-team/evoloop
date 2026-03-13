#!/usr/bin/env python3
"""
测试 Agent 异常检测 - 修正版
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
    print("🔍 测试 AnomalyDetector - 场景：点击'角色'进入错误页面")
    print("=" * 80)
    
    detector = AnomalyDetector()
    
    # 场景1: 点击后目标元素仍然可见（点击无效）
    print("\n【场景1】点击后'角色'按钮仍然可见（点击无效）")
    step = {
        "type": "action",
        "event_type": "tap",
        "target_selector": "角色",
        "payload": {"x": 0.309, "y": 0.268}
    }
    
    pre_state = {
        "elements": [{"text": "角色"}, {"text": "召唤兽"}]
    }
    
    # 点击后，"角色"还在（错误！应该跳转页面）
    post_state_fail = {
        "elements": [{"text": "角色"}, {"text": "召唤兽"}]
    }
    
    result = await detector.detect_post_execution_anomaly(
        step, pre_state, post_state_fail, "Tapped"
    )
    print(f"  检测结果: is_anomaly={result.is_anomaly}, type={result.anomaly_type}")
    if result.is_anomaly:
        print(f"  ✅ 正确检测到异常: {result.details}")
    else:
        print("  ❌ 未检测到异常")
    
    # 场景2: 点击后进入错误页面（充值中心而非角色页面）
    print("\n【场景2】点击后进入充值中心（错误页面）")
    
    # 点击后，进入了充值中心，"角色"不可见了，但也没有角色相关元素
    post_state_wrong = {
        "elements": [{"text": "充值中心"}, {"text": "50点"}, {"text": "立即购买"}]
    }
    
    result2 = await detector.detect_post_execution_anomaly(
        step, pre_state, post_state_wrong, "Tapped"
    )
    print(f"  检测结果: is_anomaly={result2.is_anomaly}, type={result2.anomaly_type}")
    print(f"  详情: {result2.details}")
    
    # 场景3: 点击后正确进入角色页面
    print("\n【场景3】点击后正确进入角色页面")
    
    post_state_correct = {
        "elements": [{"text": "角色列表"}, {"text": "龙宫"}, {"text": "129级"}]
    }
    
    result3 = await detector.detect_post_execution_anomaly(
        step, pre_state, post_state_correct, "Tapped"
    )
    print(f"  检测结果: is_anomaly={result3.is_anomaly}, type={result3.anomaly_type}")
    if not result3.is_anomaly:
        print("  ✅ 正确识别为正常状态")
    else:
        print("  ⚠️ 误报为异常")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
