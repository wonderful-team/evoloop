#!/usr/bin/env python3
"""
模拟执行 Skill 713 宏脚本，测试子步骤计时逻辑（不连接设备）
"""
import os
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
import sys
sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

import json
import asyncio
import time

# 模拟宏数据
macro_script = [
    {"step_number": 1, "type": "action", "event_type": "open_app", "source": "mobile", "payload": {"package_name": "com.netease.xyqcbg"}},
    {"step_number": 2, "type": "action", "event_type": "wait", "source": "mobile", "payload": {"duration_ms": 100}},
    {"step_number": 3, "type": "action", "event_type": "tap", "source": "mobile", "payload": {"x": 0.409, "y": 0.428}},
    {"step_number": 4, "type": "action", "event_type": "wait", "source": "mobile", "payload": {"duration_ms": 100}},
    {"step_number": 5, "type": "loop", "source": "mobile", "payload": {
        "max_iterations": 2,
        "steps": [
            {"step_number": 501, "type": "action", "event_type": "tap", "source": "mobile", "payload": {"x": 0.628, "y": 0.364}},
            {"step_number": 502, "type": "action", "event_type": "wait", "source": "mobile", "payload": {"duration_ms": 50}},
            {"step_number": 503, "type": "action", "event_type": "tap", "source": "mobile", "payload": {"x": 0.444, "y": 0.711}},
        ]
    }}
]

async def mock_execute():
    """模拟宏执行，测试子步骤计时"""

    print("=" * 80)
    print("🚀 模拟执行 Skill 713 宏脚本（测试子步骤计时）")
    print("=" * 80)
    print(f"\n📋 宏脚本结构: {len(macro_script)} 个主步骤")

    # 统计子步骤
    total_sub_steps = 0
    for step in macro_script:
        if step.get('type') == 'loop':
            payload_steps = step.get('payload', {}).get('steps', [])
            total_sub_steps += len(payload_steps)
    print(f"   总步骤数（含子步骤）: {len(macro_script) + total_sub_steps}")

    thread_id = f"mock_test_{int(time.time())}"
    step_timings = []

    async def execute_step_with_timing(step, parent_step_num: int = None, sub_index: int = None):
        """递归执行步骤并记录耗时"""
        # 处理 dict
        if isinstance(step, dict):
            step_num = step.get('step_number', 0)
            step_type = str(step.get('type', 'action'))
            event_type = step.get('event_type', 'N/A')
            target = step.get('target_selector', 'N/A')
            payload = step.get('payload', {}) if isinstance(step.get('payload'), dict) else {}
        else:
            step_num = step.step_number if hasattr(step, 'step_number') else 0
            step_type = str(step.type.value if hasattr(step.type, 'value') else step.type)
            event_type = step.event_type if hasattr(step, 'event_type') else 'N/A'
            target = step.target_selector if hasattr(step, 'target_selector') else 'N/A'
            payload = step.payload if hasattr(step, 'payload') and isinstance(step.payload, dict) else {}

        # 构建步骤编号显示
        if parent_step_num is not None and sub_index is not None:
            display_num = f"{parent_step_num}.{sub_index}"
            step_num_key = parent_step_num * 100 + sub_index
        else:
            display_num = str(step_num)
            step_num_key = step_num

        # 判断是否为 loop 步骤
        is_loop = step_type == 'loop' or str(step_type) == 'MacroStepType.LOOP'

        if is_loop:
            print(f"\n  ⏱️  Step {display_num}: [LOOP] 开始执行...")
        else:
            coords = ""
            if 'x' in payload and 'y' in payload:
                coords = f" ({payload['x']:.3f}, {payload['y']:.3f})"
            print(f"\n  ⏱️  Step {display_num}: [{step_type}] {event_type}{coords} - 开始执行...", end=" ", flush=True)

        step_start = time.time()
        loop_self_elapsed = 0
        sub_step_timings = []

        try:
            # 模拟执行步骤
            await asyncio.sleep(0.1)  # 模拟执行时间
            success = True

            loop_self_elapsed = time.time() - step_start

            # 如果是 loop，递归执行子步骤
            if is_loop:
                # 检查 steps 属性
                if isinstance(step, dict):
                    root_steps = step.get('steps', [])
                    payload_steps = step.get('payload', {}).get('steps') if isinstance(step.get('payload'), dict) else None
                else:
                    root_steps = getattr(step, 'steps', None) or []
                    payload_steps = step.payload.get('steps') if hasattr(step, 'payload') and isinstance(step.payload, dict) else None

                steps_to_use = root_steps if root_steps else (payload_steps or [])
                print(f"\n     [DEBUG] LOOP步骤检查: type={'dict' if isinstance(step, dict) else 'MacroStep'}, root_steps={len(root_steps) if root_steps else 0}, payload_steps={len(payload_steps) if payload_steps else 0}")

                if steps_to_use:
                    print(f"\n     [LOOP 开始执行 {len(steps_to_use)} 个子步骤]")
                    for idx, sub_step in enumerate(steps_to_use, 1):
                        sub_timing = await execute_step_with_timing(sub_step, step_num, idx)
                        sub_step_timings.append(sub_timing)
                        if not sub_timing['success']:
                            success = False
                            break
                    print(f"     [LOOP 子步骤执行完成]")
                else:
                    print(f"\n     [警告] LOOP步骤没有子步骤")

            # 计算总耗时
            elapsed = time.time() - step_start

            if not is_loop:
                status_icon = "✅" if success else "❌"
                print(f"{status_icon} 完成 ({elapsed:.2f}s)")

            # 记录耗时
            timing = {
                'step_number': step_num_key,
                'display_num': display_num,
                'type': step_type,
                'event_type': event_type,
                'target': target,
                'elapsed_ms': int(elapsed * 1000),
                'success': success,
                'is_loop': is_loop,
                'is_sub_step': parent_step_num is not None,
                'parent_step': parent_step_num,
                'sub_steps': sub_step_timings if is_loop else [],
                'loop_self_ms': int(loop_self_elapsed * 1000) if is_loop else None,
                'sub_steps_total_ms': int((elapsed - loop_self_elapsed) * 1000) if is_loop and sub_step_timings else None,
                'sub_step_count': len(sub_step_timings) if is_loop else 0
            }

            return timing

        except Exception as e:
            elapsed = time.time() - step_start
            if not is_loop:
                print(f"❌ 异常 ({elapsed:.2f}s): {e}")
            else:
                print(f"\n     [LOOP 异常 ({elapsed:.2f}s): {e}]")

            return {
                'step_number': step_num_key,
                'display_num': display_num,
                'type': step_type,
                'event_type': event_type,
                'target': target,
                'elapsed_ms': int(elapsed * 1000),
                'success': False,
                'is_loop': is_loop,
                'is_sub_step': parent_step_num is not None,
                'parent_step': parent_step_num,
                'error': str(e)
            }

    print("\n" + "=" * 80)
    print("⚡ 开始执行 (将记录每步耗时)")
    print("=" * 80)

    # 执行所有主步骤
    for step in macro_script:
        timing = await execute_step_with_timing(step)
        step_timings.append(timing)

    # 显示结果
    print(f"\n{'=' * 80}")
    print("📊 执行结果")
    print("=" * 80)

    # 显示每步耗时详情
    if step_timings:
        print(f"\n{'=' * 80}")
        print("⏱️  每步执行耗时详情")
        print("=" * 80)
        print(f"\n{'步骤':<10} {'类型':<12} {'事件':<15} {'耗时':<10} {'状态'}")
        print("-" * 80)

        def print_timing(t, indent=0):
            prefix = "  " * indent
            step_num = f"{prefix}Step {t['display_num']}"
            step_type = t['type'][:11]
            event = (t['event_type'][:14] if t['event_type'] else 'N/A') if t.get('event_type') else 'N/A'
            elapsed = f"{t['elapsed_ms']/1000:.2f}s"
            status = "✅" if t['success'] else "❌"

            print(f"{step_num:<10} {step_type:<12} {event:<15} {elapsed:<10} {status}")

            # LOOP 步骤显示时间分解
            if t.get('is_loop') and t.get('sub_steps'):
                if t.get('loop_self_ms') is not None:
                    sub_total = t.get('sub_steps_total_ms', 0) / 1000
                    print(f"{prefix}           └─ LOOP本身: {t['loop_self_ms']/1000:.2f}s | 子步骤合计: {sub_total:.2f}s ({t.get('sub_step_count', 0)}个)")

            # 打印子步骤
            if t.get('sub_steps'):
                for sub in t['sub_steps']:
                    print_timing(sub, indent + 1)

        for t in step_timings:
            print_timing(t)

        # 统计信息
        def count_steps(timings):
            count = len(timings)
            total = sum(t['elapsed_ms'] for t in timings)
            for t in timings:
                if t.get('sub_steps'):
                    sub_count, sub_total = count_steps(t['sub_steps'])
                    count += sub_count
                    total += sub_total
            return count, total

        total_steps, total_time = count_steps(step_timings)
        avg_time = total_time / total_steps if total_steps > 0 else 0

        print(f"\n{'=' * 80}")
        print("📈 耗时统计")
        print("=" * 80)
        print(f"  总步骤数（含子步骤）: {total_steps}")
        print(f"  总耗时: {total_time/1000:.2f}s")
        print(f"  平均每步: {avg_time/1000:.2f}s")

if __name__ == "__main__":
    asyncio.run(mock_execute())
