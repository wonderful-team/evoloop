#!/usr/bin/env python3
"""
Skill 713 完整分析 - 包含验证阶段 + 执行阶段的详细耗时
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
verification_step_logs: List[Dict[str, Any]] = []
execution_step_logs: List[Dict[str, Any]] = []


def patch_llm_calls():
    """拦截 LLM 调用记录参数和响应"""
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
                request_info = {
                    "call_id": call_id,
                    "timestamp": time.strftime("%H:%M:%S"),
                    "model": getattr(llm, 'model_name', getattr(llm, 'model', 'unknown')),
                    "system_prompt": "",
                    "user_prompt": "",
                }

                for msg in messages:
                    if hasattr(msg, 'type') and hasattr(msg, 'content'):
                        if msg.type == 'system':
                            request_info["system_prompt"] = msg.content[:800] + "..." if len(msg.content) > 800 else msg.content
                        elif msg.type == 'human':
                            request_info["user_prompt"] = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content

                print(f"\n{'='*80}")
                print(f"🤖 LLM 调用 #{call_id} | 模型: {request_info['model']} | 时间: {request_info['timestamp']}")
                print(f"{'='*80}")
                print(f"\n【System Prompt 预览】")
                print(request_info['system_prompt'][:600])
                if len(request_info['system_prompt']) > 600:
                    print(f"... ({len(request_info['system_prompt']) - 600} 字符省略)")

                print(f"\n【User Prompt】")
                print(request_info['user_prompt'])

                try:
                    response = await original_ainvoke(messages, **invoke_kwargs)
                    elapsed_ms = int((time.time() - start_time) * 1000)

                    response_content = response.content if hasattr(response, 'content') else str(response)

                    request_info["response_preview"] = response_content[:500]
                    request_info["elapsed_ms"] = elapsed_ms
                    request_info["success"] = True

                    print(f"\n{'-'*80}")
                    print(f"✅ LLM 调用完成 | 耗时: {elapsed_ms}ms")
                    print(f"{'-'*80}")
                    print(f"【Response 预览】")
                    print(response_content[:400] + "..." if len(response_content) > 400 else response_content)

                    llm_call_logs.append(request_info)
                    return response

                except Exception as e:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    request_info["error"] = str(e)
                    request_info["elapsed_ms"] = elapsed_ms
                    request_info["success"] = False

                    print(f"\n{'-'*80}")
                    print(f"❌ LLM 调用失败 | 耗时: {elapsed_ms}ms | 错误: {e}")

                    llm_call_logs.append(request_info)
                    raise

            llm.ainvoke = patched_ainvoke
            return llm

        LLMFactory.create_llm = patched_create_llm
        print("✅ LLM 调用拦截器已安装\n")

    except Exception as e:
        print(f"⚠️ LLM 拦截器安装失败: {e}")


async def run_verification(macro_script: List[Dict]) -> Dict[str, Any]:
    """阶段 1: 运行验证"""
    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    print("=" * 80)
    print("🔍 阶段 1: Agent 验证 (Verification)")
    print("=" * 80)
    print("说明: 在真实执行前，Agent 会预演宏脚本，检测异常并生成适配策略\n")

    request = VerificationRequest(
        macro_script=macro_script,
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="HYC5T19B11003570"
        ),
        max_rounds=1,
        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=2,
            allow_strategy_adaptation=True,
            enable_screenshot_analysis=True
        )
    )

    verification_start = time.time()
    validator = AgentMacroValidator(request)
    response = await validator.validate()
    verification_elapsed = int((time.time() - verification_start) * 1000)

    print(f"\n{'='*80}")
    print(f"📊 验证阶段完成 | 耗时: {verification_elapsed}ms ({verification_elapsed/1000:.2f}s)")
    print(f"{'='*80}")

    return {
        "response": response,
        "elapsed_ms": verification_elapsed
    }


async def run_execution(macro_script: List[Dict]) -> Dict[str, Any]:
    """阶段 2: 执行宏"""
    from app.core.execution.macro.engine import MacroEngine
    from app.core.execution.macro.schema import MacroScript

    print("\n" + "=" * 80)
    print("⚡ 阶段 2: 宏执行 (Execution)")
    print("=" * 80)
    print("说明: 在真实设备上执行宏脚本，记录每步实际耗时\n")

    # 创建 MacroScript
    script = MacroScript(steps=macro_script)

    thread_id = f"skill_713_analysis_{int(time.time())}"
    step_timings = []

    total_start = time.time()

    # 递归执行并记录每步耗时
    async def execute_with_timing(step, parent_step_num: int = None, sub_index: int = None):
        from app.core.execution.macro.schema import MacroStepType

        step_num = step.step_number if hasattr(step, 'step_number') else step.get('step_number', 0)
        step_type = str(step.type.value if hasattr(step, 'type') and hasattr(step.type, 'value') else step.get('type', 'action'))
        event_type = step.event_type if hasattr(step, 'event_type') else step.get('event_type', 'N/A')
        target = step.target_selector if hasattr(step, 'target_selector') else step.get('target_selector', 'N/A')

        if parent_step_num is not None and sub_index is not None:
            display_num = f"{parent_step_num}.{sub_index}"
        else:
            display_num = str(step_num)

        is_loop = 'loop' in step_type.lower()

        print(f"\n  ⏱️  Step {display_num}: [{event_type or 'N/A'}] {target or 'N/A'} - 开始")

        step_start = time.time()
        sub_step_timings = []
        success = True

        try:
            if is_loop:
                print(f"     [LOOP 步骤，执行 {len(step.steps if hasattr(step, 'steps') else step.get('steps', []))} 个子步骤]")
                steps_to_execute = step.steps if hasattr(step, 'steps') else step.get('steps', [])
                for idx, sub_step in enumerate(steps_to_execute, 1):
                    sub_timing = await execute_with_timing(sub_step, step_num, idx)
                    sub_step_timings.append(sub_timing)
                    if not sub_timing['success']:
                        success = False
                        break
                # LOOP 本身不通过 MacroEngine 执行，只执行子步骤
                loop_elapsed = time.time() - step_start
            else:
                # 通过 MacroEngine 执行单步
                success, msg, fallback = await MacroEngine.execute_steps(
                    thread_id=thread_id,
                    steps=[step],
                    params={},
                    extracted_data={},
                    disable_ocr=True
                )

            elapsed_ms = int((time.time() - step_start) * 1000)
            status_icon = "✅" if success else "❌"
            print(f"     {status_icon} 完成 | 耗时: {elapsed_ms}ms")

            return {
                'step_number': step_num,
                'display_num': display_num,
                'type': step_type,
                'event_type': event_type,
                'target': target,
                'elapsed_ms': elapsed_ms,
                'success': success,
                'is_loop': is_loop,
                'is_sub_step': parent_step_num is not None,
                'sub_steps': sub_step_timings if is_loop else [],
            }

        except Exception as e:
            elapsed_ms = int((time.time() - step_start) * 1000)
            print(f"     ❌ 异常 | 耗时: {elapsed_ms}ms | 错误: {e}")
            return {
                'step_number': step_num,
                'display_num': display_num,
                'type': step_type,
                'event_type': event_type,
                'target': target,
                'elapsed_ms': elapsed_ms,
                'success': False,
                'error': str(e)
            }

    # 执行所有步骤
    for step in script.steps:
        timing = await execute_with_timing(step)
        step_timings.append(timing)

    total_elapsed = int((time.time() - total_start) * 1000)

    print(f"\n{'='*80}")
    print(f"📊 执行阶段完成 | 总耗时: {total_elapsed}ms ({total_elapsed/1000:.2f}s)")
    print(f"{'='*80}")

    return {
        "step_timings": step_timings,
        "elapsed_ms": total_elapsed
    }


async def analyze():
    """完整分析: 验证 + 执行"""

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

    # ========== 阶段 1: 验证 ==========
    verification_result = await run_verification(macro_script)
    verification_response = verification_result["response"]

    # 验证阶段 LLM 统计
    print("\n【验证阶段 LLM 调用统计】")
    if llm_call_logs:
        verification_llm_time = sum(log.get('elapsed_ms', 0) for log in llm_call_logs)
        print(f"  调用次数: {len(llm_call_logs)}")
        print(f"  LLM 总耗时: {verification_llm_time}ms")
        print(f"  平均耗时: {verification_llm_time/len(llm_call_logs):.0f}ms")
    else:
        print("  无 LLM 调用（验证过程未触发 LLM 适配）")

    # 验证阶段步骤结果
    if verification_response.verification_report and verification_response.verification_report.rounds:
        round_report = verification_response.verification_report.rounds[0]
        print(f"\n【验证阶段步骤结果】")
        print(f"  通过: {round_report.passed_steps} | 适配: {round_report.adapted_steps} | 失败: {round_report.failed_steps}")

        print(f"\n  {'步骤':<8} {'事件':<12} {'状态':<12} {'适配次数'}")
        print("  " + "-" * 50)
        for sr in round_report.step_results:
            step = sr.original_step
            step_num = step.get('step_number', sr.step_number)
            event_type = step.get('event_type', 'unknown')
            status = sr.status.value
            adaptations = len(sr.adaptations)
            print(f"  {step_num:<8} {event_type:<12} {status:<12} {adaptations}")

    # ========== 阶段 2: 执行 ==========
    execution_result = await run_execution(macro_script)
    step_timings = execution_result["step_timings"]

    # 执行阶段耗时详情
    print("\n【执行阶段每步耗时详情】")
    print(f"\n  {'步骤':<10} {'类型':<12} {'事件':<15} {'耗时(ms)':<12} {'状态'}")
    print("  " + "-" * 70)

    def print_timing(t, indent=0):
        prefix = "  " * indent
        step_num = f"{prefix}{t['display_num']}"
        step_type = t['type'][:11]
        event = (t['event_type'][:14] if t.get('event_type') else 'N/A') if t.get('event_type') else 'N/A'
        elapsed = f"{t['elapsed_ms']}"
        status = "✅" if t['success'] else "❌"
        print(f"  {step_num:<8} {step_type:<12} {event:<15} {elapsed:<12} {status}")

        if t.get('sub_steps'):
            for sub in t['sub_steps']:
                print_timing(sub, indent + 1)

    for t in step_timings:
        print_timing(t)

    # ========== 总结 ==========
    print("\n" + "=" * 80)
    print("📈 完整分析总结")
    print("=" * 80)

    verification_time = verification_result["elapsed_ms"]
    execution_time = execution_result["elapsed_ms"]
    total_time = verification_time + execution_time

    print(f"\n【时间分配】")
    print(f"  验证阶段: {verification_time}ms ({verification_time/total_time*100:.1f}%)")
    print(f"  执行阶段: {execution_time}ms ({execution_time/total_time*100:.1f}%)")
    print(f"  总计: {total_time}ms ({total_time/1000:.2f}s)")

    if llm_call_logs:
        total_llm_time = sum(log.get('elapsed_ms', 0) for log in llm_call_logs)
        print(f"\n【LLM 调用】")
        print(f"  总调用次数: {len(llm_call_logs)}")
        print(f"  LLM 总耗时: {total_llm_time}ms")
        print(f"  LLM 平均耗时: {total_llm_time/len(llm_call_logs):.0f}ms")

        print(f"\n  {'#':<5} {'模型':<25} {'耗时(ms)':<12} {'状态'}")
        print("  " + "-" * 60)
        for log in llm_call_logs:
            print(f"  {log['call_id']:<5} {log['model']:<25} {log['elapsed_ms']:<12} {'✅' if log['success'] else '❌'}")

    print(f"\n【执行模式建议】")
    if verification_response.execution_mode.value == "agentic":
        print("  AGENTIC - 需要 Agent 实时监控执行")
    elif verification_response.execution_mode.value == "hybrid":
        print("  HYBRID - 部分步骤需要 Agent 介入")
    else:
        print("  DETERMINISTIC - 可直接执行")

    print("\n" + "=" * 80)
    print("✅ 分析完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(analyze())
