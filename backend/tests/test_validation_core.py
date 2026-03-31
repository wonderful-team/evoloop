#!/usr/bin/env python3
"""
直接测试验证核心逻辑，绕过复杂依赖
"""

import os
import sys
import json
import asyncio
import importlib.util
from pathlib import Path

os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

# 加载 .env
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


# Mock 所有阻碍导入的模块
class MockModule:
    def __getattr__(self, name):
        return MockModule()
    def __call__(self, *args, **kwargs):
        return MockModule()

for mod in ['sqlmodel', 'langchain_anthropic', 'langchain_core', 'langchain',
            'app.infrastructure.llm', 'app.core.context', 'app.core.db',
            'app.infrastructure.config', 'app.core.execution.terminal',
            'app.core.execution.sandbox', 'app.infrastructure.automation']:
    sys.modules[mod] = MockModule()


async def test_core_logic():
    """测试核心验证逻辑"""
    print("=" * 70)
    print("🔬 Agent Macro Validator - 核心逻辑测试（Mock模式）")
    print("=" * 70)

    # 1. 加载数据库
    print("\n🗄️  加载 Skill 713...")
    try:
        import asyncpg

        pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
        pg_port = os.environ.get("POSTGRES_PORT", "5432")
        pg_db = os.environ.get("POSTGRES_DB", "app")
        pg_user = os.environ.get("POSTGRES_USER", "postgres")
        pg_password = os.environ.get("POSTGRES_PASSWORD", "")
        db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

        conn = await asyncpg.connect(db_url)
        row = await conn.fetchrow(
            "SELECT id, name, macro_script FROM learned_skills WHERE id = $1", 713
        )
        await conn.close()

        if row:
            macro_data = row['macro_script']
            if isinstance(macro_data, str):
                macro_script = json.loads(macro_data)
            else:
                macro_script = macro_data

            print(f"✅ 加载成功: {row['name']}")
            print(f"   步骤数: {len(macro_script)}")
        else:
            print("❌ Skill 713 不存在")
            return False
    except Exception as e:
        print(f"❌ 数据库错误: {e}")
        return False

    # 2. 加载并测试核心组件
    print("\n🔧 测试核心组件...")

    BASE_PATH = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/execution/macro")

    # 加载 verification_models
    try:
        spec = importlib.util.spec_from_file_location("vm", BASE_PATH / "verification_models.py")
        vm = importlib.util.module_from_spec(spec)
        sys.modules["vm"] = vm
        spec.loader.exec_module(vm)
        print("✅ verification_models 加载成功")
        print(f"   - AnomalyType: {len(list(vm.AnomalyType))} 种异常类型")
        print(f"   - ExecutionMode: {list(vm.ExecutionMode)}")
    except Exception as e:
        print(f"❌ verification_models 加载失败: {e}")
        return False

    # 加载 anomaly_detector
    try:
        spec = importlib.util.spec_from_file_location("ad", BASE_PATH / "anomaly_detector.py")
        ad = importlib.util.module_from_spec(spec)
        sys.modules["ad"] = ad

        # 手动注入依赖
        for name in ['AnomalyType', 'AnomalyDetectionResult', 'ExecutionMode']:
            ad.__dict__[name] = getattr(vm, name)
        ad.__dict__['Optional'] = type('Optional', (), {'__getitem__': lambda self, x: x})()
        ad.__dict__['Dict'] = dict
        ad.__dict__['Any'] = object

        spec.loader.exec_module(ad)
        print("✅ anomaly_detector 加载成功")

        # 测试异常检测
        detector = ad.AnomalyDetector()

        # 模拟 UI 状态
        ui_state = {
            "platform": "android",
            "elements": [
                {"text": "Login", "bounds": {"center_x": 500, "center_y": 1000}},
                {"text": "Username", "bounds": {"center_x": 500, "center_y": 800}}
            ]
        }

        # 测试步骤 - 元素不存在的情况
        step_missing = {
            "step_number": 1,
            "event_type": "tap",
            "target_selector": "#missing-button",
            "payload": {"selector": "#missing-button", "x": 100, "y": 200}
        }

        result = await detector.detect_pre_execution_anomaly(step_missing, ui_state)
        print(f"\n   异常检测测试:")
        print(f"   - 步骤: tap #missing-button")
        print(f"   - 是否异常: {result.is_anomaly}")
        print(f"   - 异常类型: {result.anomaly_type}")
        print(f"   - 置信度: {result.confidence}")

    except Exception as e:
        print(f"❌ anomaly_detector 测试失败: {e}")
        import traceback
        traceback.print_exc()

    # 3. 显示宏步骤分析
    print("\n📋 Skill 713 宏步骤分析:")
    for i, step in enumerate(macro_script, 1):
        event_type = step.get('event_type', 'unknown')
        payload = step.get('payload', {})

        if event_type == 'open_app':
            print(f"   {i}. 🚀 打开应用: {payload.get('package', 'unknown')}")
        elif event_type == 'tap':
            coords = f"({payload.get('x')}, {payload.get('y')})" if 'x' in payload else "未知"
            selector = step.get('target_selector', '无')
            print(f"   {i}. 👆 点击: {coords} | 目标: {selector}")
        elif event_type == 'wait':
            print(f"   {i}. ⏱️  等待: {payload.get('seconds', 0)}秒")
        else:
            print(f"   {i}. ❓ 未知: {event_type}")

    # 4. 模拟验证流程
    print("\n🔍 模拟验证流程:")
    print("   1. 初始化 VerificationWorker (连接手机)")
    print("   2. 执行 Step 1: open_app")
    print("      - 检查 app 是否启动")
    print("      - 检测超时异常")
    print("   3. 执行 Step 2: wait")
    print("      - 等待指定时间")
    print("   4. 执行 Step 3: tap")
    print("      - 检查目标元素是否存在")
    print("      - 如不存在，尝试 Adaptation")
    print("      - 执行点击")
    print("      - 验证 UI 变化")
    print("   5. 生成验证报告")

    print("\n" + "=" * 70)
    print("⚠️  注意：当前为 Mock 模式，未真正执行手机操作")
    print("   要真实执行，需要:")
    print("   - 安装完整依赖 (langchain, pydantic-settings, etc.)")
    print("   - 启动 MobileController 服务")
    print("   - 连接手机并获取 device_id")
    print("=" * 70)

    return True


if __name__ == "__main__":
    result = asyncio.run(test_core_logic())
    sys.exit(0 if result else 1)
