#!/usr/bin/env python3
"""
模拟测试子步骤耗时记录逻辑（无需实际设备）
"""
import os
import sys
import asyncio
import time

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


async def test_substep_timing():
    """测试子步骤耗时记录逻辑"""
    print("=" * 80)
    print("🧪 测试子步骤耗时记录逻辑")
    print("=" * 80)

    # 模拟步骤数据
    mock_steps = [
        {"step_number": 1, "type": "action", "event_type": "open_app", "target_selector": None, "payload": {"app_name": "test"}},
        {"step_number": 2, "type": "action", "event_type": "wait", "target_selector": None, "payload": {"seconds": 0.1}},
        {
            "step_number": 3,
            "type": "loop",
            "event_type": "loop",
            "target_selector": None,
            "payload": {"max_iterations": 2},
            "steps": [
                {"step_number": 1, "type": "action", "event_type": "tap", "target_selector": "btn1", "payload": {"x": 0.5, "y": 0.5}},
                {"step_number": 2, "type": "action", "event_type": "wait", "target_selector": None, "payload": {"seconds": 0.05}},
                {"step_number": 3, "type": "action", "event_type": "tap", "target_selector": "btn2", "payload": {"x": 0.6, "y": 0.6}},
            ]
        },
        {"step_number": 4, "type": "action", "event_type": "wait", "target_selector": None, "payload": {"seconds": 0.1}},
    ]

    step_timings = []

    async def execute_step_with_timing(step, parent_step_num=None, sub_index=None):
        """递归执行步骤并记录耗时"""
        if isinstance(step, dict):
            step_num = step.get('step_number', 0)
            step_type = str(step.get('type', 'action'))
            event_type = step.get('event_type', 'N/A')
            target = step.get('target_selector', 'N/A')
            payload = step.get('payload', {}) if isinstance(step.get('payload'), dict) else {}
        else:
            step_num = getattr(step, 'step_number', 0)
            step_type = str(step.type.value if hasattr(step.type, 'value') else step.type)
            event_type = getattr(step, 'event_type', 'N/A')
            target = getattr(step, 'target_selector', 'N/A')
            payload = step.payload if hasattr(step, 'payload') and isinstance(step.payload, dict) else {}

        if parent_step_num is not None and sub_index is not None:
            display_num = f"{parent_step_num}.{sub_index}"
            step_num_key = parent_step_num * 100 + sub_index
        else:
            display_num = str(step_num)
            step_num_key = step_num

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
        success = True

        try:
            if is_loop:
                print(f"[模拟 LOOP 执行]")
                loop_self_elapsed = 0.001  # 模拟 LOOP 本身的开销

                if isinstance(step, dict):
                    root_steps = step.get('steps', [])
                else:
                    root_steps = getattr(step, 'steps', None) or []

                steps_to_use = root_steps if root_steps else []
                print(f"     [LOOP 有 {len(steps_to_use)} 个子步骤]")

                if steps_to_use:
                    print(f"     [LOOP 开始执行子步骤]")
                    for idx, sub_step in enumerate(steps_to_use, 1):
                        sub_timing = await execute_step_with_timing(sub_step, step_num, idx)
                        sub_step_timings.append(sub_timing)
                        if not sub_timing['success']:
                            success = False
                            break
                    print(f"     [LOOP 子步骤执行完成]")
            else:
                # 模拟非 LOOP 步骤执行
                duration = payload.get('seconds', 0.01)
                await asyncio.sleep(duration)
                print(f"✅ 完成 ({duration:.2f}s)")

            elapsed = time.time() - step_start

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
            print(f"❌ 异常 ({elapsed:.2f}s): {e}")
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

    # 执行所有步骤
    print("\n⚡ 开始执行模拟步骤...")
    for step in mock_steps:
        timing = await execute_step_with_timing(step)
        step_timings.append(timing)

    # 显示结果
    print(f"\n{'=' * 80}")
    print("📊 执行结果")
    print("=" * 80)

    def print_timing(t, indent=0):
        prefix = "  " * indent
        step_num = f"{prefix}Step {t['display_num']}"
        step_type = t['type'][:11]
        event = (t['event_type'][:14] if t.get('event_type') else 'N/A') if t.get('event_type') else 'N/A'
        elapsed = f"{t['elapsed_ms']/1000:.2f}s"
        status = "✅" if t['success'] else "❌"

        print(f"{step_num:<10} {step_type:<12} {event:<15} {elapsed:<10} {status}")

        if t.get('is_loop') and t.get('sub_steps'):
            if t.get('loop_self_ms') is not None:
                sub_total = t.get('sub_steps_total_ms', 0) / 1000
                print(f"{prefix}           └─ LOOP本身: {t['loop_self_ms']/1000:.3f}s | 子步骤合计: {sub_total:.3f}s ({t.get('sub_step_count', 0)}个)")

            for sub in t.get('sub_steps', []):
                print_timing(sub, indent + 1)

    print(f"\n{'步骤':<10} {'类型':<12} {'事件':<15} {'耗时':<10} {'状态'}")
    print("-" * 80)
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

    print(f"\n{'=' * 80}")
    print("📈 耗时统计")
    print("=" * 80)
    print(f"  总步骤数（含子步骤）: {total_steps}")
    print(f"  总耗时: {total_time/1000:.2f}s")
    print(f"  平均每步: {total_time/total_steps/1000:.3f}s" if total_steps > 0 else "  N/A")

    # 找出最慢步骤
    def get_all_timings(timings):
        all_timings = []
        for t in timings:
            all_timings.append(t)
            if t.get('sub_steps'):
                all_timings.extend(get_all_timings(t['sub_steps']))
        return all_timings

    all_timings = get_all_timings(step_timings)
    if all_timings:
        sorted_by_time = sorted(all_timings, key=lambda x: x['elapsed_ms'], reverse=True)
        print(f"  最慢步骤: Step {sorted_by_time[0]['display_num']} ({sorted_by_time[0]['elapsed_ms']/1000:.3f}s)")
        print(f"  最快步骤: Step {sorted_by_time[-1]['display_num']} ({sorted_by_time[-1]['elapsed_ms']/1000:.3f}s)")

    success = all(t['success'] for t in step_timings)
    if success:
        print("\n✅ 模拟执行成功！")
    else:
        print("\n❌ 模拟执行失败")

    return step_timings


if __name__ == "__main__":
    asyncio.run(test_substep_timing())
