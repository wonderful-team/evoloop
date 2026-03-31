#!/usr/bin/env python3
"""
执行修正后的 Skill 713 宏脚本（带详细耗时记录，包括子步骤）
"""

import os
import sys
import json
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


async def execute_skill_713():
    """执行 Skill 713 宏脚本"""

    # 从数据库加载修正后的宏
    import asyncpg
    pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "app")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

    conn = await asyncpg.connect(db_url)
    row = await conn.fetchrow(
        """SELECT id, name, macro_script, execution_mode, confidence_score
           FROM learned_skills WHERE id = $1""",
        713
    )
    await conn.close()

    print("=" * 80)
    print("🚀 执行 Skill 713 宏脚本")
    print("=" * 80)
    print(f"\n任务: {row['name']}")
    print(f"执行模式: {row['execution_mode']}")
    print(f"置信度: {row['confidence_score']:.2f}")

    # 解析宏脚本
    macro_script = json.loads(row['macro_script'])
    print(f"\n📋 宏脚本结构: {len(macro_script)} 个主步骤")

    # 统计子步骤
    total_sub_steps = 0
    for step in macro_script:
        if step.get('type') == 'loop':
            total_sub_steps += len(step.get('steps', []))
    print(f"   总步骤数（含子步骤）: {len(macro_script) + total_sub_steps}")

    # 显示将要执行的步骤
    print("\n📝 执行计划:")
    for i, step in enumerate(macro_script, 1):
        step_type = step.get('type', 'action')
        event_type = step.get('event_type', step.get('action', 'unknown'))
        target = step.get('target_selector', 'N/A')
        payload = step.get('payload', {})

        if step_type == 'loop':
            sub_count = len(step.get('steps', []))
            print(f"\n  Step {i}: [LOOP] 数据采集循环 ({sub_count} 个子步骤)")
            for j, sub in enumerate(step.get('steps', []), 1):
                sub_event = sub.get('event_type', sub.get('action', 'unknown'))
                sub_target = sub.get('target_selector', 'N/A')
                sub_payload = sub.get('payload', {})
                coords = ""
                if 'x' in sub_payload and 'y' in sub_payload:
                    coords = f"({sub_payload['x']:.3f}, {sub_payload['y']:.3f})"
                print(f"     {j}. [{sub_event}] {sub_target} {coords}")
        else:
            coords = ""
            if 'x' in payload and 'y' in payload:
                coords = f"({payload['x']:.3f}, {payload['y']:.3f})"
            print(f"\n  Step {i}: [{event_type.upper()}] {target} {coords}")

    # 执行宏
    print("\n" + "=" * 80)
    print("⚡ 开始执行 (将记录每步耗时)")
    print("=" * 80)

    # 导入并执行
    from app.core.execution.macro.engine import MacroEngine
    from app.core.execution.macro.schema import MacroScript, MacroStep, MacroStepType

    thread_id = f"skill_713_execution_{int(time.time())}"
    step_timings = []

    total_start_time = time.time()

    try:
        # 创建 MacroScript
        print("\n[DEBUG] 创建 MacroScript 前检查 steps:")
        for i, s in enumerate(macro_script[:3], 1):
            print(f"  Step {i}: type={s.get('type')}, source={s.get('source')}, event_type={s.get('event_type')}")
        script = MacroScript(steps=macro_script)
        print("[DEBUG] MacroScript 创建成功，检查转换后的 steps:")
        for i, s in enumerate(script.steps[:3], 1):
            print(f"  Step {i}: type={s.type}, source={s.source}, event_type={s.event_type}")

        # 递归执行步骤并记录耗时
        async def execute_step_with_timing(step, parent_step_num: int = None, sub_index: int = None):
            """递归执行步骤并记录耗时"""
            # 处理 dict 或 MacroStep 对象
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
                source_info = step.get('source') if isinstance(step, dict) else getattr(step, 'source', None)
                print(f"\n  ⏱️  Step {display_num}: [{step_type}] {event_type} source={source_info}{coords} - 开始执行...", end=" ", flush=True)

            step_start = time.time()
            loop_self_elapsed = 0  # LOOP 步骤本身的执行时间
            sub_step_timings = []
            success = True
            msg = ""

            try:
                # 执行步骤
                source_info = step.get('source') if isinstance(step, dict) else getattr(step, 'source', None)
                print(f"[DEBUG] Step {display_num}: source={source_info}, type={step_type}, event={event_type}")

                # 对于 LOOP 步骤，我们不通过 MacroEngine 执行，而是手动执行以分离子步骤计时
                if is_loop:
                    print(f"[DEBUG] LOOP步骤，手动执行以分离子步骤计时")
                    # LOOP 步骤本身的开销（条件检查等）
                    loop_self_elapsed = 0.01  # 近似值，实际 LOOP 控制逻辑很快
                    success = True
                    msg = ""

                    # 获取子步骤
                    if isinstance(step, dict):
                        root_steps = step.get('steps', [])
                        payload_steps = step.get('payload', {}).get('steps') if isinstance(step.get('payload'), dict) else None
                    else:
                        root_steps = getattr(step, 'steps', None) or []
                        payload_steps = step.payload.get('steps') if hasattr(step, 'payload') and isinstance(step.payload, dict) else None

                    steps_to_use = root_steps if root_steps else (payload_steps or [])
                    print(f"\n     [DEBUG] LOOP步骤检查: {len(steps_to_use)} 个子步骤")

                    if steps_to_use:
                        print(f"\n     [LOOP 开始执行 {len(steps_to_use)} 个子步骤]")
                        for idx, sub_step in enumerate(steps_to_use, 1):
                            sub_timing = await execute_step_with_timing(sub_step, step_num, idx)
                            sub_step_timings.append(sub_timing)
                            if not sub_timing['success']:
                                success = False
                                msg = f"子步骤 {idx} 失败"
                                break
                        print(f"     [LOOP 子步骤执行完成]")
                    else:
                        print(f"\n     [警告] LOOP步骤没有子步骤")
                else:
                    # 非 LOOP 步骤，通过 MacroEngine 执行
                    print(f"[DEBUG] 调用 MacroEngine.execute_steps for Step {display_num}")
                    success, msg, fallback = await MacroEngine.execute_steps(
                        thread_id=thread_id,
                        steps=[step],
                        params={},
                        extracted_data={},
                        disable_ocr=True
                    )
                    print(f"[DEBUG] MacroEngine.execute_steps 返回: success={success}")

                # 计算总耗时（包括子步骤）
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
                    # LOOP 步骤的详细时间分解
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

        # 执行所有主步骤
        for step in script.steps:
            timing = await execute_step_with_timing(step)
            step_timings.append(timing)

        total_elapsed = time.time() - total_start_time
        success = all(t['success'] for t in step_timings)

        # 显示结果
        print(f"\n{'=' * 80}")
        print("📊 执行结果")
        print("=" * 80)
        print(f"\n总执行时间: {total_elapsed:.2f}s")
        print(f"成功: {success}")

        # 显示每步耗时详情（包括子步骤）
        if step_timings:
            print(f"\n{'=' * 80}")
            print("⏱️  每步执行耗时详情")
            print("=" * 80)
            print(f"\n{'步骤':<10} {'类型':<12} {'事件':<15} {'耗时':<10} {'状态'}")
            print("-" * 80)

            # 递归打印步骤
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

            # 找出最慢的步骤
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
                print(f"  最慢步骤: Step {sorted_by_time[0]['display_num']} ({sorted_by_time[0]['elapsed_ms']/1000:.2f}s)")
                print(f"  最快步骤: Step {sorted_by_time[-1]['display_num']} ({sorted_by_time[-1]['elapsed_ms']/1000:.2f}s)")

        if success:
            print("\n✅ 宏执行成功！")
        else:
            print("\n❌ 宏执行失败")

        return {"success": success, "step_timings": step_timings}

    except Exception as e:
        total_elapsed = time.time() - total_start_time
        print(f"\n❌ 执行异常 ({total_elapsed:.2f}s): {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}


if __name__ == "__main__":
    asyncio.run(execute_skill_713())
