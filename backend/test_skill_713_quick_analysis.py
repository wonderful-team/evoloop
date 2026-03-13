#!/usr/bin/env python3
"""
Skill 713 快速分析 - 只执行前几步展示 LLM 调用日志和耗时分析
"""

import os
import sys
import json
import asyncio
import time
from typing import Any, Dict, List, Optional
from functools import wraps

os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

def load_env_file():
    from pathlib import Path
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

# 全局日志
llm_call_logs: List[Dict[str, Any]] = []
step_logs: List[Dict[str, Any]] = []


def patch_llm_calls():
    """Patch LLM calls to log requests and responses"""
    try:
        from app.infrastructure.llm.factory import LLMFactory

        original_create_llm = LLMFactory.create_llm

        @wraps(original_create_llm)
        def patched_create_llm(*args, **kwargs):
            llm = original_create_llm(*args, **kwargs)
            if llm is None:
                return None

            original_ainvoke = llm.ainvoke

            @wraps(original_ainvoke)
            async def patched_ainvoke(messages, **invoke_kwargs):
                call_id = len(llm_call_logs) + 1
                start_time = time.time()

                # 提取请求信息
                request_data = {
                    "call_id": call_id,
                    "model": getattr(llm, 'model_name', getattr(llm, 'model', 'unknown')),
                }

                # 转换消息
                for i, msg in enumerate(messages):
                    if hasattr(msg, 'type') and hasattr(msg, 'content'):
                        request_data[f"message_{i}_role"] = msg.type
                        content = msg.content
                        # 只显示前1500字符
                        request_data[f"message_{i}_content"] = content[:1500] + "..." if len(content) > 1500 else content

                print(f"\n{'='*80}")
                print(f"🤖 LLM 调用 #{call_id} 开始 - 模型: {request_data['model']}")
                print(f"{'='*80}")

                # 打印提示词
                for i, msg in enumerate(messages):
                    if hasattr(msg, 'type') and hasattr(msg, 'content'):
                        print(f"\n--- [{msg.type.upper()}] ---")
                        content = msg.content
                        lines = content.split('\n')
                        for line in lines[:25]:
                            print(line)
                        if len(lines) > 25:
                            print(f"... ({len(lines) - 25} 行省略)")

                try:
                    response = await original_ainvoke(messages, **invoke_kwargs)
                    elapsed_ms = int((time.time() - start_time) * 1000)

                    response_content = response.content if hasattr(response, 'content') else str(response)

                    request_data["response"] = response_content[:1000] + "..." if len(response_content) > 1000 else response_content
                    request_data["elapsed_ms"] = elapsed_ms
                    request_data["success"] = True

                    print(f"\n{'-'*80}")
                    print(f"✅ LLM 调用 #{call_id} 完成 - 耗时: {elapsed_ms}ms")
                    print(f"{'-'*80}")
                    print(f"响应预览: {response_content[:300]}...")

                    llm_call_logs.append(request_data)
                    return response

                except Exception as e:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    request_data["error"] = str(e)
                    request_data["elapsed_ms"] = elapsed_ms
                    request_data["success"] = False

                    print(f"\n{'-'*80}")
                    print(f"❌ LLM 调用 #{call_id} 失败 - 耗时: {elapsed_ms}ms")
                    print(f"错误: {e}")

                    llm_call_logs.append(request_data)
                    raise

            llm.ainvoke = patched_ainvoke
            return llm

        LLMFactory.create_llm = patched_create_llm
        print("✅ LLM 调用拦截器已安装\n")

    except Exception as e:
        print(f"⚠️ LLM 拦截器安装失败: {e}")


async def analyze():
    """快速分析"""

    patch_llm_calls()

    # 加载 Skill
    import asyncpg
    pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "app")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

    conn = await asyncpg.connect(db_url)
    row = await conn.fetchrow(
        """SELECT id, name, macro_script FROM learned_skills WHERE id = $1""",
        713
    )
    await conn.close()

    if not row:
        print("❌ Skill 713 不存在")
        return

    print("=" * 80)
    print(f"📋 Skill 713: {row['name']}")
    print("=" * 80)

    macro_script = json.loads(row['macro_script']) if isinstance(row['macro_script'], str) else row['macro_script']
    print(f"宏步骤数: {len(macro_script)}")

    # 运行验证
    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    request = VerificationRequest(
        macro_script=macro_script,
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="HYC5T19B11003570"
        ),
        max_rounds=1,
        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=1,  # 减少重试以加快速度
            allow_strategy_adaptation=True,
            enable_screenshot_analysis=True
        )
    )

    print("\n" + "=" * 80)
    print("🧪 开始验证 (带详细耗时分析)")
    print("=" * 80)

    total_start = time.time()
    validator = AgentMacroValidator(request)
    response = await validator.validate()
    total_elapsed = int((time.time() - total_start) * 1000)

    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 验证结果汇总")
    print("=" * 80)
    print(f"总成功: {response.success}")
    print(f"执行模式: {response.execution_mode}")
    print(f"总耗时: {total_elapsed}ms ({total_elapsed/1000:.2f}s)")

    # LLM 调用汇总
    print("\n" + "=" * 80)
    print("🤖 LLM 调用汇总")
    print("=" * 80)

    if llm_call_logs:
        total_llm_time = sum(log.get('elapsed_ms', 0) for log in llm_call_logs)
        print(f"\n总调用次数: {len(llm_call_logs)}")
        print(f"LLM 总耗时: {total_llm_time}ms")
        print(f"平均耗时: {total_llm_time/len(llm_call_logs):.0f}ms")

        print(f"\n{'#':<5} {'模型':<25} {'耗时(ms)':<12} {'状态'}")
        print("-" * 80)
        for log in llm_call_logs:
            print(f"{log['call_id']:<5} {log['model']:<25} {log['elapsed_ms']:<12} {'✅' if log['success'] else '❌'}")
    else:
        print("\n无 LLM 调用记录（可能未触发异常，无需 LLM 适配）")

    # 步骤结果
    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]

        print("\n" + "=" * 80)
        print("⏱️  每步验证结果")
        print("=" * 80)

        print(f"\n{'步骤':<8} {'事件':<12} {'状态':<12} {'适配次数'}")
        print("-" * 80)
        for sr in round_report.step_results:
            step = sr.original_step
            step_num = step.get('step_number', sr.step_number)
            event_type = step.get('event_type', 'unknown')
            status = sr.status.value
            adaptations = len(sr.adaptations)
            print(f"{step_num:<8} {event_type:<12} {status:<12} {adaptations}")

            if sr.adaptations:
                for i, adapt in enumerate(sr.adaptations, 1):
                    print(f"         └─ 适配 {i}: {adapt.reasoning[:50]}...")

    print("\n" + "=" * 80)
    print("✅ 分析完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(analyze())
