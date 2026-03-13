#!/usr/bin/env python3
"""
Skill 713 详细分析报告 - 包含 LLM 调用日志和每步验证耗时
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

# 全局 LLM 调用日志
llm_call_logs: List[Dict[str, Any]] = []
step_verification_logs: List[Dict[str, Any]] = []


def patch_llm_calls():
    """Patch LLM calls to log requests and responses"""
    try:
        from app.infrastructure.llm.factory import LLMFactory
        from langchain_core.messages import BaseMessage

        original_create_llm = LLMFactory.create_llm

        @wraps(original_create_llm)
        def patched_create_llm(*args, **kwargs):
            llm = original_create_llm(*args, **kwargs)
            if llm is None:
                return None

            # 包装 ainvoke 方法
            original_ainvoke = llm.ainvoke

            @wraps(original_ainvoke)
            async def patched_ainvoke(messages, **invoke_kwargs):
                call_id = len(llm_call_logs) + 1
                start_time = time.time()

                # 记录请求参数
                request_data = {
                    "call_id": call_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "model": getattr(llm, 'model_name', getattr(llm, 'model', 'unknown')),
                    "messages": []
                }

                # 转换消息为可序列化格式
                for msg in messages:
                    if hasattr(msg, 'type') and hasattr(msg, 'content'):
                        request_data["messages"].append({
                            "role": msg.type,
                            "content": msg.content[:2000] if len(msg.content) > 2000 else msg.content  # 限制长度
                        })
                    else:
                        request_data["messages"].append({"type": str(type(msg)), "content": str(msg)[:2000]})

                # 添加额外参数
                if invoke_kwargs:
                    request_data["invoke_kwargs"] = {k: str(v) for k, v in invoke_kwargs.items()}

                print(f"\n{'='*80}")
                print(f"🤖 LLM 调用 #{call_id} 开始")
                print(f"{'='*80}")
                print(f"模型: {request_data['model']}")
                print(f"\n请求参数:")
                for msg in request_data["messages"]:
                    print(f"\n  [{msg['role'].upper()}]:")
                    content = msg['content']
                    # 格式化打印，限制行数
                    lines = content.split('\n')
                    for line in lines[:30]:  # 最多显示30行
                        print(f"    {line}")
                    if len(lines) > 30:
                        print(f"    ... ({len(lines) - 30} 行省略)")

                try:
                    # 调用原始方法
                    response = await original_ainvoke(messages, **invoke_kwargs)
                    elapsed_ms = int((time.time() - start_time) * 1000)

                    # 记录响应
                    response_content = ""
                    if hasattr(response, 'content'):
                        response_content = response.content
                    elif isinstance(response, str):
                        response_content = response
                    else:
                        response_content = str(response)

                    request_data["response"] = {
                        "content": response_content[:2000] if len(response_content) > 2000 else response_content,
                        "elapsed_ms": elapsed_ms
                    }
                    request_data["success"] = True

                    print(f"\n{'-'*80}")
                    print(f"✅ LLM 调用 #{call_id} 完成 (耗时: {elapsed_ms}ms)")
                    print(f"{'-'*80}")
                    print(f"\n响应内容:")
                    lines = response_content.split('\n')
                    for line in lines[:20]:  # 最多显示20行
                        print(f"  {line}")
                    if len(lines) > 20:
                        print(f"  ... ({len(lines) - 20} 行省略)")

                    llm_call_logs.append(request_data)
                    return response

                except Exception as e:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    request_data["error"] = str(e)
                    request_data["success"] = False
                    request_data["elapsed_ms"] = elapsed_ms

                    print(f"\n{'-'*80}")
                    print(f"❌ LLM 调用 #{call_id} 失败 (耗时: {elapsed_ms}ms)")
                    print(f"{'-'*80}")
                    print(f"错误: {e}")

                    llm_call_logs.append(request_data)
                    raise

            llm.ainvoke = patched_ainvoke
            return llm

        LLMFactory.create_llm = patched_create_llm
        print("✅ LLM 调用拦截器已安装")

    except Exception as e:
        print(f"⚠️ 无法安装 LLM 拦截器: {e}")


class StepVerificationProfiler:
    """用于记录每一步验证的详细耗时"""

    def __init__(self):
        self.current_step = None
        self.step_timings = []

    def start_step(self, step_number: int, step_info: Dict[str, Any]):
        """开始记录一步的验证"""
        self.current_step = {
            "step_number": step_number,
            "step_info": step_info,
            "start_time": time.time(),
            "phases": []
        }
        print(f"\n{'='*80}")
        print(f"⏱️  Step {step_number} 验证开始: [{step_info.get('event_type', 'unknown').upper()}] {step_info.get('target_selector', 'N/A')}")
        print(f"{'='*80}")

    def record_phase(self, phase_name: str, details: Optional[Dict] = None):
        """记录一个阶段的耗时"""
        if self.current_step is None:
            return

        now = time.time()
        phase = {
            "name": phase_name,
            "timestamp": now,
            "elapsed_ms": int((now - self.current_step["start_time"]) * 1000),
            "details": details or {}
        }
        self.current_step["phases"].append(phase)
        print(f"  [{phase['elapsed_ms']:>6}ms] {phase_name}")
        if details:
            for k, v in details.items():
                print(f"           {k}: {v}")

    def end_step(self, success: bool, result: Optional[Dict] = None):
        """结束一步的验证记录"""
        if self.current_step is None:
            return

        end_time = time.time()
        total_ms = int((end_time - self.current_step["start_time"]) * 1000)

        self.current_step["end_time"] = end_time
        self.current_step["total_ms"] = total_ms
        self.current_step["success"] = success
        self.current_step["result"] = result or {}

        self.step_timings.append(self.current_step)

        status_icon = "✅" if success else "❌"
        print(f"\n  {'-'*40}")
        print(f"  {status_icon} Step {self.current_step['step_number']} 验证完成 - 总耗时: {total_ms}ms")
        print(f"  {'='*80}")

        step_verification_logs.append(self.current_step)
        self.current_step = None

        return total_ms


# 创建全局 profiler
profiler = StepVerificationProfiler()


def patch_verification_worker():
    """Patch VerificationWorker to add detailed logging"""
    try:
        from app.core.execution.macro.verification_worker import VerificationWorker
        from app.core.execution.macro.agent_validator import AgentMacroValidator

        # Patch VerificationWorker.execute_step
        original_execute_step = VerificationWorker.execute_step

        @wraps(original_execute_step)
        async def patched_execute_step(self, step: Dict[str, Any], round_config: Any = None):
            step_number = step.get('step_number', 0)
            step_type = step.get('type', 'action')
            event_type = step.get('event_type', 'unknown')
            target = step.get('target_selector', 'N/A')
            payload = step.get('payload', {})

            print(f"\n{'='*80}")
            print(f"🔍 Agent 验证 Step {step_number}: [{event_type.upper()}] {target}")
            print(f"{'='*80}")
            print(f"  步骤类型: {step_type}")
            print(f"  事件类型: {event_type}")
            print(f"  目标: {target}")
            if payload:
                print(f"  Payload: {json.dumps(payload, ensure_ascii=False)[:200]}")

            step_start = time.time()

            try:
                # 调用原始方法
                result = await original_execute_step(self, step, round_config)

                elapsed_ms = int((time.time() - step_start) * 1000)

                # 解析结果
                status = "unknown"
                error = None
                if isinstance(result, dict):
                    status = result.get('status', 'unknown')
                    error = result.get('error')
                elif hasattr(result, 'status'):
                    status = result.status
                    if hasattr(result, 'error'):
                        error = result.error

                print(f"\n  ⏱️  耗时: {elapsed_ms}ms | 状态: {status}")
                if error:
                    print(f"  ⚠️  错误: {error}")

                return result

            except Exception as e:
                elapsed_ms = int((time.time() - step_start) * 1000)
                print(f"\n  ❌ 异常 ({elapsed_ms}ms): {e}")
                raise

        VerificationWorker.execute_step = patched_execute_step

        # Patch AgentMacroValidator._execute_step_with_adaptation
        if hasattr(AgentMacroValidator, '_execute_step_with_adaptation'):
            original_execute_with_adapt = AgentMacroValidator._execute_step_with_adaptation

            @wraps(original_execute_with_adapt)
            async def patched_execute_with_adapt(self, step: Dict[str, Any], step_number: int, round_config: Any):
                event_type = step.get('event_type', 'unknown')
                target = step.get('target_selector', 'N/A')

                print(f"\n{'─'*80}")
                print(f"🤖 Agent 适配处理 Step {step_number}: [{event_type.upper()}] {target}")
                print(f"{'─'*80}")

                # 执行原始方法
                result = await original_execute_with_adapt(self, step, step_number, round_config)

                # 打印适配结果
                print(f"\n  📊 Step {step_number} 适配结果:")
                print(f"     状态: {result.status.value}")
                print(f"     适配次数: {len(result.adaptations)}")

                if result.adaptations:
                    for i, adapt in enumerate(result.adaptations, 1):
                        print(f"     适配 #{i}: {adapt.reasoning[:80]}...")

                if result.error_message:
                    print(f"     错误: {result.error_message}")

                print(f"{'─'*80}")

                return result

            AgentMacroValidator._execute_step_with_adaptation = patched_execute_with_adapt

        print("✅ VerificationWorker 和 AgentMacroValidator 日志拦截器已安装")

    except Exception as e:
        print(f"⚠️ 无法安装拦截器: {e}")
        import traceback
        traceback.print_exc()


async def analyze_skill_713():
    """分析 Skill 713 的完整信息，包含详细耗时"""

    # 安装拦截器
    patch_llm_calls()
    patch_verification_worker()

    # 1. 从数据库加载 Skill
    import asyncpg
    pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "app")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

    conn = await asyncpg.connect(db_url)
    row = await conn.fetchrow(
        """SELECT id, name, description, status, execution_mode, confidence_score,
                  macro_script
           FROM learned_skills WHERE id = $1""",
        713
    )
    await conn.close()

    if not row:
        print("❌ Skill 713 不存在")
        return

    print("=" * 80)
    print("📋 Skill 713 详细信息")
    print("=" * 80)
    print(f"\nID: {row['id']}")
    print(f"名称: {row['name']}")
    print(f"描述: {row['description'] or 'N/A'}")
    print(f"状态: {row['status']}")
    print(f"执行模式: {row['execution_mode']}")
    print(f"置信度评分: {row['confidence_score']}")

    # 解析宏脚本
    macro_script_data = row['macro_script']
    if isinstance(macro_script_data, str):
        macro_script = json.loads(macro_script_data)
    else:
        macro_script = macro_script_data

    print(f"\n📊 宏脚本统计:")
    print(f"   主步骤数: {len(macro_script)}")

    # 统计子步骤
    total_sub_steps = 0
    loop_count = 0
    for step in macro_script:
        if step.get('type') == 'loop':
            loop_count += 1
            sub_steps = len(step.get('steps', []))
            total_sub_steps += sub_steps
            print(f"   Loop {loop_count}: {sub_steps} 子步骤")

    print(f"   总步骤数（含子步骤）: {len(macro_script) + total_sub_steps}")

    # 2. 运行验证测试
    print("\n" + "=" * 80)
    print("🧪 Agent 验证测试 (带详细耗时分析)")
    print("=" * 80)

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
            max_retries_per_step=2,
            allow_strategy_adaptation=True,
            enable_screenshot_analysis=True
        )
    )

    total_start_time = time.time()
    validator = AgentMacroValidator(request)
    response = await validator.validate()
    total_elapsed_ms = int((time.time() - total_start_time) * 1000)

    # 3. 打印详细结果
    print("\n" + "=" * 80)
    print("📊 验证结果汇总")
    print("=" * 80)
    print(f"\n整体成功: {response.success}")
    print(f"验证状态: {response.status}")
    print(f"执行模式: {response.execution_mode}")
    print(f"置信度: {response.confidence_score:.2f}")
    print(f"总耗时: {total_elapsed_ms}ms ({total_elapsed_ms/1000:.2f}s)")

    # 4. 每步详细耗时
    print("\n" + "=" * 80)
    print("⏱️  每步验证详细耗时")
    print("=" * 80)

    if step_verification_logs:
        print(f"\n{'步骤':<8} {'事件':<12} {'目标':<20} {'总耗时(ms)':<12} {'状态'}")
        print("-" * 80)
        for log in step_verification_logs:
            step_num = log['step_number']
            event = log['step_info']['event_type'][:11]
            target = log['step_info']['target_selector'][:18]
            total_ms = log['total_ms']
            status = "✅" if log['success'] else "❌"
            print(f"{step_num:<8} {event:<12} {target:<20} {total_ms:<12} {status}")

            # 打印每个阶段
            if log.get('phases'):
                for phase in log['phases']:
                    phase_name = phase['name'][:25]
                    elapsed = phase['elapsed_ms']
                    print(f"         └─ {phase_name:<25} @{elapsed}ms")

    # 5. LLM 调用汇总
    print("\n" + "=" * 80)
    print("🤖 LLM 调用汇总")
    print("=" * 80)

    if llm_call_logs:
        print(f"\n总 LLM 调用次数: {len(llm_call_logs)}")
        total_llm_time = sum(log.get('response', {}).get('elapsed_ms', 0) for log in llm_call_logs)
        print(f"LLM 总耗时: {total_llm_time}ms ({total_llm_time/1000:.2f}s)")
        print(f"平均每次调用: {total_llm_time/len(llm_call_logs):.0f}ms")

        print(f"\n{'调用#':<8} {'模型':<20} {'耗时(ms)':<12} {'状态'}")
        print("-" * 80)
        for log in llm_call_logs:
            call_id = log['call_id']
            model = log.get('model', 'unknown')[:18]
            elapsed = log.get('response', {}).get('elapsed_ms', log.get('elapsed_ms', 0))
            status = "✅" if log.get('success') else "❌"
            print(f"{call_id:<8} {model:<20} {elapsed:<12} {status}")
    else:
        print("\n没有 LLM 调用记录（可能使用 QuickFix 策略）")

    # 6. 适配详情
    round_report = None
    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]

        print(f"\n{'='*80}")
        print("🔧 适配详情")
        print(f"{'='*80}")
        print(f"\n步骤执行统计:")
        print(f"  通过: {round_report.passed_steps}")
        print(f"  适配: {round_report.adapted_steps}")
        print(f"  失败: {round_report.failed_steps}")
        print(f"  跳过: {round_report.skipped_steps}")

        if round_report.step_results:
            print(f"\n每步详细结果:")
            for sr in round_report.step_results:
                step = sr.original_step
                step_num = step.get('step_number', sr.step_number)
                event_type = step.get('event_type', 'unknown')
                target = step.get('target_selector', 'N/A')

                status_icon = "✅" if sr.status.value == "passed" else "🔧" if sr.status.value == "adapted" else "❌"
                print(f"\n  {status_icon} Step {step_num}: [{event_type.upper()}] {target}")
                print(f"     状态: {sr.status.value}")

                if sr.adaptations:
                    print(f"     Agent 介入:")
                    for i, adapt in enumerate(sr.adaptations, 1):
                        print(f"       [{i}] {adapt.reasoning}")
                        if adapt.success and 'payload' in adapt.adapted_strategy:
                            p = adapt.adapted_strategy['payload']
                            if 'x' in p and 'original_x' in p:
                                print(f"           坐标修正: ({p['original_x']}, {p['original_y']}) -> ({p['x']}, {p['y']})")

                if sr.error_message:
                    print(f"     错误: {sr.error_message}")

    # 7. 性能分析总结
    print("\n" + "=" * 80)
    print("📈 性能分析总结")
    print("=" * 80)

    if step_verification_logs:
        step_times = [log['total_ms'] for log in step_verification_logs]
        avg_step_time = sum(step_times) / len(step_times)
        max_step_time = max(step_times)
        min_step_time = min(step_times)

        print(f"\n步骤执行时间统计:")
        print(f"  总步骤数: {len(step_times)}")
        print(f"  平均耗时: {avg_step_time:.0f}ms")
        print(f"  最快步骤: {min_step_time}ms")
        print(f"  最慢步骤: {max_step_time}ms")

        # 找出最慢的步骤
        slowest_step = max(step_verification_logs, key=lambda x: x['total_ms'])
        print(f"\n  最慢步骤详情:")
        print(f"    Step {slowest_step['step_number']}: [{slowest_step['step_info']['event_type'].upper()}]")
        print(f"    目标: {slowest_step['step_info']['target_selector']}")
        print(f"    耗时: {slowest_step['total_ms']}ms")

    print(f"\n时间分配:")
    print(f"  总验证耗时: {total_elapsed_ms}ms")
    if llm_call_logs:
        llm_time = sum(log.get('response', {}).get('elapsed_ms', 0) for log in llm_call_logs)
        other_time = total_elapsed_ms - llm_time
        print(f"  LLM 调用耗时: {llm_time}ms ({llm_time/total_elapsed_ms*100:.1f}%)")
        print(f"  其他操作耗时: {other_time}ms ({other_time/total_elapsed_ms*100:.1f}%)")

    # 8. 总结
    print("\n" + "=" * 80)
    print("✅ 验证结论")
    print("=" * 80)

    if response.success:
        print("宏验证成功，可以在目标设备上稳定执行")
    else:
        print("宏验证未通过，需要进一步优化")

    if response.execution_mode.value == "agentic":
        print("建议执行模式: AGENTIC (需要 Agent 实时监控)")
    elif response.execution_mode.value == "hybrid":
        print("建议执行模式: HYBRID (部分步骤需要 Agent 介入)")
    else:
        print("建议执行模式: DETERMINISTIC (可直接执行)")


if __name__ == "__main__":
    asyncio.run(analyze_skill_713())
