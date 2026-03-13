#!/usr/bin/env python3
"""
测试 Agent 异常检测和修正
"""

import os
import sys
import json
import asyncio
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


async def test_anomaly_detection():
    from app.core.execution.macro.anomaly_detector import AnomalyDetector
    from app.core.execution.macro.verification_models import AnomalyType
    
    print("=" * 80)
    print("🔍 测试 AnomalyDetector")
    print("=" * 80)
    
    detector = AnomalyDetector()
    
    # 模拟 Step 3: tap "角色" 
    step = {
        "type": "action",
        "event_type": "tap",
        "target_selector": "角色",
        "source": "mobile",
        "payload": {"x": 0.309, "y": 0.268},
        "step_number": 3
    }
    
    # 模拟执行前状态 (藏宝阁首页)
    pre_state = {
        "platform": "android",
        "package_name": "com.netease.cbg",
        "current_activity": ".react.activity.CbgReactHomeActivity",
        "elements": [
            {"text": "梦幻币", "resource_id": ""},
            {"text": "角色", "resource_id": ""},
            {"text": "召唤兽", "resource_id": ""},
        ]
    }
    
    # 模拟执行后状态 (充值中心 - 错误页面!)
    post_state = {
        "platform": "android", 
        "package_name": "com.netease.cbg",
        "current_activity": ".react.activity.CbgReactHomeActivity",
        "elements": [
            {"text": "充值中心", "resource_id": ""},
            {"text": "50点", "resource_id": ""},
            {"text": "100点", "resource_id": ""},
            {"text": "立即购买", "resource_id": ""},
        ]
    }
    
    print("\n【Step 3】点击'角色'")
    print(f"  执行前页面: 藏宝阁首页 (有'角色'按钮)")
    print(f"  执行后页面: 充值中心 (有'立即购买'按钮)")
    print()
    
    # 执行前检测
    print("🔍 执行前异常检测...")
    pre_result = await detector.detect_pre_execution_anomaly(step, pre_state)
    print(f"  是否异常: {pre_result.is_anomaly}")
    print(f"  异常类型: {pre_result.anomaly_type}")
    
    # 执行后检测
    print("\n🔍 执行后异常检测...")
    post_result = await detector.detect_post_execution_anomaly(
        step=step,
        pre_state=pre_state,
        post_state=post_state,
        execution_result="Tapped at (333, 627)"
    )
    print(f"  是否异常: {post_result.is_anomaly}")
    print(f"  异常类型: {post_result.anomaly_type}")
    print(f"  置信度: {post_result.confidence}")
    print(f"  建议动作: {post_result.suggested_action}")
    print(f"  详情: {post_result.details}")
    
    # 检查是否检测到 STATE_MISMATCH
    if post_result.is_anomaly and post_result.anomaly_type == AnomalyType.STATE_MISMATCH:
        print("\n✅ Agent 检测到状态不匹配!")
        print("   应该触发适配策略来修正")
    else:
        print("\n❌ Agent 没有检测到状态不匹配")
        print("   问题: 检测器只检查状态是否变化，不检查是否进入正确页面")


async def main():
    await test_anomaly_detection()


if __name__ == "__main__":
    asyncio.run(main())
