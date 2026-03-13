"""
宏脚本优化器测试

测试 MacroOptimizer 的各种优化策略
"""

import pytest
import json
from pathlib import Path
from app.core.execution.macro.optimizer import MacroOptimizer, OptimizationResult


class TestMacroOptimizer:
    """测试 MacroOptimizer"""

    def test_empty_script(self):
        """测试空脚本"""
        optimizer = MacroOptimizer()
        result, stats = optimizer.optimize([])

        assert result == []
        assert stats.original_steps == 0
        assert stats.optimized_steps == 0

    def test_single_step_no_change(self):
        """测试单步骤（无优化）"""
        optimizer = MacroOptimizer()
        macro = [
            {"step_number": 1, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}}
        ]

        result, stats = optimizer.optimize(macro)

        assert len(result) == 1
        assert stats.reduction_ratio == 0.0
        assert stats.removed_steps == 0

    def test_merge_adjacent_waits(self):
        """测试合并相邻 wait 步骤"""
        optimizer = MacroOptimizer()
        macro = [
            {"step_number": 1, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 100}},
            {"step_number": 3, "type": "action", "event_type": "wait", "payload": {"duration_ms": 200}},
            {"step_number": 4, "type": "action", "event_type": "wait", "payload": {"duration_ms": 300}},
            {"step_number": 5, "type": "action", "event_type": "tap", "payload": {"x": 0.3, "y": 0.3}},
        ]

        result, stats = optimizer.optimize(macro)

        print(f"\nMerge waits test:")
        print(f"  Original: {stats.original_steps} steps")
        print(f"  Optimized: {stats.optimized_steps} steps")
        print(f"  Merged: {stats.merged_steps}")

        # 应该合并 3 个 wait 为 1 个
        assert stats.merged_steps == 2  # 合并了2个步骤
        assert len(result) == 3  # tap + merged_wait + tap

        # 检查合并后的 wait 时间
        wait_step = result[1]
        assert wait_step['event_type'] == 'wait'
        assert wait_step['payload']['duration_ms'] == 600  # 100+200+300

    def test_remove_duplicate_taps(self):
        """测试去除重复 tap 操作"""
        optimizer = MacroOptimizer()
        macro = [
            {"step_number": 1, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 100}},
            {"step_number": 3, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}},  # 重复
            {"step_number": 4, "type": "action", "event_type": "tap", "payload": {"x": 0.3, "y": 0.3}},
        ]

        result, stats = optimizer.optimize(macro)

        print(f"\nRemove duplicates test:")
        print(f"  Original: {stats.original_steps} steps")
        print(f"  Optimized: {stats.optimized_steps} steps")
        print(f"  Removed: {stats.removed_steps}")

        # 应该去除第3步（重复）
        assert stats.removed_steps >= 1

    def test_filter_redundant_mouse_moves(self):
        """测试过滤冗余 mouse_move"""
        optimizer = MacroOptimizer()
        macro = [
            {"step_number": 1, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}},
            {"step_number": 2, "type": "action", "event_type": "mouse_move", "payload": {"x": 0.4, "y": 0.4}},
            {"step_number": 3, "type": "action", "event_type": "cursor_move", "payload": {"x": 0.3, "y": 0.3}},
            {"step_number": 4, "type": "action", "event_type": "tap", "payload": {"x": 0.3, "y": 0.3}},
        ]

        result, stats = optimizer.optimize(macro)

        print(f"\nFilter redundant test:")
        print(f"  Original: {stats.original_steps} steps")
        print(f"  Optimized: {stats.optimized_steps} steps")

        # 应该过滤掉 mouse_move 和 cursor_move
        event_types = [s.get('event_type') for s in result]
        assert 'mouse_move' not in event_types
        assert 'cursor_move' not in event_types

    def test_short_wait_extension(self):
        """测试短 wait 延长到最小值"""
        optimizer = MacroOptimizer(min_interval_ms=500)
        macro = [
            {"step_number": 1, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 50}},  # 太短
            {"step_number": 3, "type": "action", "event_type": "tap", "payload": {"x": 0.3, "y": 0.3}},
        ]

        result, stats = optimizer.optimize(macro)

        print(f"\nShort wait extension test:")
        print(f"  Time saved: {stats.time_saved_ms}ms")

        # 50ms 应该被延长到 100ms（MIN_WAIT_DURATION_MS）
        wait_step = result[1]
        assert wait_step['payload']['duration_ms'] >= 100

    def test_coalesce_extract_operations(self):
        """测试合并提取操作"""
        optimizer = MacroOptimizer(enable_all_strategies=True)
        macro = [
            {"step_number": 1, "type": "extract", "source": "global", "key": "data_1", "extract_type": "dump_ui"},
            {"step_number": 2, "type": "extract", "source": "global", "key": "data_2", "extract_type": "dump_ui"},
            {"step_number": 3, "type": "extract", "source": "global", "key": "data_3", "extract_type": "dump_ui"},
            {"step_number": 4, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}},
        ]

        result, stats = optimizer.optimize(macro)

        print(f"\nCoalesce extracts test:")
        print(f"  Original: {stats.original_steps} steps")
        print(f"  Optimized: {stats.optimized_steps} steps")

        # 应该合并 3 个 extract 为 1 个 batch (uses first extract_type with batch flag in payload)
        extract_steps = [s for s in result if s.get('type') == 'extract']
        assert len(extract_steps) == 1
        assert extract_steps[0].get('extract_type') == 'dump_ui'  # Uses first extract's type
        assert extract_steps[0].get('payload', {}).get('batch') == True
        assert extract_steps[0].get('payload', {}).get('count') == 3

    def test_comprehensive_optimization(self):
        """综合优化测试（模拟藏宝阁技能宏脚本）"""
        optimizer = MacroOptimizer()

        # 模拟原始宏脚本（包含多种冗余）
        macro = [
            # Phase 1: 启动APP
            {"step_number": 1, "type": "action", "event_type": "open_app", "source": "global", "payload": {"package": "com.netease.xyqcbg", "wait_ms": 3000}},
            {"step_number": 2, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 500}},
            {"step_number": 3, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 500}},  # 冗余

            # Phase 2: 处理弹窗
            {"step_number": 4, "type": "action", "event_type": "tap", "source": "global", "payload": {"x": 0.741, "y": 0.134}},
            {"step_number": 5, "type": "action", "event_type": "mouse_move", "source": "global", "payload": {"x": 0.7, "y": 0.2}},  # 冗余
            {"step_number": 6, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 1000}},
            {"step_number": 7, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 500}},  # 可合并

            # Phase 3: 进入角色列表
            {"step_number": 8, "type": "action", "event_type": "tap", "source": "global", "payload": {"x": 0.278, "y": 0.089}},
            {"step_number": 9, "type": "action", "event_type": "tap", "source": "global", "payload": {"x": 0.278, "y": 0.089}},  # 重复
            {"step_number": 10, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 3000}},

            # Phase 4: 数据提取
            {"step_number": 11, "type": "extract", "source": "global", "key": "ui_dump_1", "extract_type": "dump_ui"},
            {"step_number": 12, "type": "action", "event_type": "swipe", "source": "global", "payload": {"x": 0.5, "y": 0.8, "x2": 0.5, "y2": 0.3}},
            {"step_number": 13, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 1000}},
            {"step_number": 14, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 1000}},  # 可合并

            {"step_number": 15, "type": "extract", "source": "global", "key": "ui_dump_2", "extract_type": "dump_ui"},
            {"step_number": 16, "type": "action", "event_type": "swipe", "source": "global", "payload": {"x": 0.5, "y": 0.8, "x2": 0.5, "y2": 0.3}},
            {"step_number": 17, "type": "action", "event_type": "wait", "source": "global", "payload": {"duration_ms": 2000}},

            {"step_number": 18, "type": "extract", "source": "global", "key": "ui_dump_3", "extract_type": "dump_ui"},
            {"step_number": 19, "type": "dump", "source": "global", "payload": {"path": "{{output_path}}"}},
        ]

        result, stats = optimizer.optimize(macro)

        print("\n" + "=" * 60)
        print("综合优化测试（藏宝阁技能宏脚本）")
        print("=" * 60)
        print(f"原始步骤数: {stats.original_steps}")
        print(f"优化后步骤数: {stats.optimized_steps}")
        print(f"减少比例: {stats.reduction_ratio:.1%}")
        print(f"合并步骤: {stats.merged_steps}")
        print(f"移除步骤: {stats.removed_steps}")
        print(f"节省时间: {stats.time_saved_ms}ms")
        print(f"应用策略: {', '.join(stats.strategies_applied)}")
        print("=" * 60)

        # 验证优化效果
        assert stats.reduction_ratio > 0.10  # 至少减少 10%
        assert len(result) < len(macro)

        # 验证步骤重新编号
        for i, step in enumerate(result, 1):
            assert step['step_number'] == i

        return result, stats

    def test_quick_optimize_classmethod(self):
        """测试快速优化类方法"""
        macro = [
            {"step_number": 1, "type": "action", "event_type": "wait", "payload": {"duration_ms": 100}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 200}},
            {"step_number": 3, "type": "action", "event_type": "tap", "payload": {"x": 0.5, "y": 0.5}},
        ]

        result = MacroOptimizer.quick_optimize(macro)

        # 应该合并两个 wait
        assert len(result) == 2
        assert result[0]['event_type'] == 'wait'
        assert result[0]['payload']['duration_ms'] == 300


class TestOptimizationScenarios:
    """场景测试"""

    def test_scenario_cbg_role_extraction(self):
        """
        测试藏宝阁角色提取场景

        模拟实际录制生成的宏脚本，包含多种冗余
        """
        print("\n" + "=" * 60)
        print("场景测试: 藏宝阁角色提取宏优化")
        print("=" * 60)

        # 模拟从录制生成的原始宏（有很多冗余）
        raw_macro = [
            # APP启动阶段
            {"step_number": 1, "type": "action", "event_type": "open_app", "source": "global", "payload": {"package": "com.netease.xyqcbg"}},
            {"step_number": 2, "type": "action", "event_type": "wait", "payload": {"duration_ms": 100}},  # 太短
            {"step_number": 3, "type": "action", "event_type": "wait", "payload": {"duration_ms": 200}},
            {"step_number": 4, "type": "action", "event_type": "wait", "payload": {"duration_ms": 300}},  # 可合并
            {"step_number": 5, "type": "action", "event_type": "mouse_move", "payload": {"x": 0.5, "y": 0.5}},  # 冗余

            # 弹窗处理
            {"step_number": 6, "type": "action", "event_type": "tap", "payload": {"x": 0.741, "y": 0.134}},
            {"step_number": 7, "type": "action", "event_type": "cursor_move", "payload": {"x": 0.7, "y": 0.3}},  # 冗余
            {"step_number": 8, "type": "action", "event_type": "wait", "payload": {"duration_ms": 500}},
            {"step_number": 9, "type": "action", "event_type": "wait", "payload": {"duration_ms": 500}},  # 可合并

            # 进入角色列表
            {"step_number": 10, "type": "action", "event_type": "tap", "payload": {"x": 0.278, "y": 0.089}},
            {"step_number": 11, "type": "action", "event_type": "tap", "payload": {"x": 0.278, "y": 0.089}},  # 重复点击
            {"step_number": 12, "type": "action", "event_type": "tap", "payload": {"x": 0.278, "y": 0.089}},  # 再次重复
            {"step_number": 13, "type": "action", "event_type": "wait", "payload": {"duration_ms": 2000}},
            {"step_number": 14, "type": "action", "event_type": "wait", "payload": {"duration_ms": 1000}},  # 可合并

            # 数据提取 - 第1页
            {"step_number": 15, "type": "extract", "source": "global", "key": "ui_1", "extract_type": "dump_ui"},
            {"step_number": 16, "type": "action", "event_type": "swipe", "payload": {"x": 0.5, "y": 0.8, "x2": 0.5, "y2": 0.3}},
            {"step_number": 17, "type": "action", "event_type": "wait", "payload": {"duration_ms": 800}},
            {"step_number": 18, "type": "action", "event_type": "wait", "payload": {"duration_ms": 700}},  # 可合并
            {"step_number": 19, "type": "action", "event_type": "wait", "payload": {"duration_ms": 500}},  # 可合并

            # 数据提取 - 第2页
            {"step_number": 20, "type": "extract", "source": "global", "key": "ui_2", "extract_type": "dump_ui"},
            {"step_number": 21, "type": "action", "event_type": "swipe", "payload": {"x": 0.5, "y": 0.8, "x2": 0.5, "y2": 0.3}},
            {"step_number": 22, "type": "action", "event_type": "wait", "payload": {"duration_ms": 1500}},

            # 数据提取 - 第3页
            {"step_number": 23, "type": "extract", "source": "global", "key": "ui_3", "extract_type": "dump_ui"},
            {"step_number": 24, "type": "dump", "payload": {"path": "~/output.json"}},
        ]

        optimizer = MacroOptimizer()
        optimized, stats = optimizer.optimize(raw_macro)

        print(f"\n优化结果:")
        print(f"  原始: {stats.original_steps} 步骤")
        print(f"  优化后: {stats.optimized_steps} 步骤")
        print(f"  减少: {stats.reduction_ratio:.1%}")
        print(f"  合并: {stats.merged_steps} 步骤")
        print(f"  移除: {stats.removed_steps} 步骤")
        print(f"  节省时间: {stats.time_saved_ms}ms")

        # 详细对比
        print(f"\n详细对比:")
        print(f"  {'原始步骤':<30} -> {'优化后步骤':<30}")
        print(f"  {'-'*30} -> {'-'*30}")

        # 显示优化前后的对比
        for i, (orig, opt) in enumerate(zip(raw_macro[:10], optimized[:10])):
            orig_desc = f"{orig['type']}: {orig.get('event_type', orig.get('extract_type', 'unknown'))}"
            opt_desc = f"{opt['type']}: {opt.get('event_type', opt.get('extract_type', 'unknown'))}"
            marker = "✓" if i < len(optimized) else "✗"
            print(f"  {orig_desc:<30} -> {opt_desc:<30} {marker}")

        if len(raw_macro) > 10:
            print(f"  ... ({len(raw_macro) - 10} more steps)")

        # 验证
        assert stats.reduction_ratio >= 0.20  # 至少减少 20%
        assert stats.merged_steps >= 3  # 至少合并 3 个 wait
        assert stats.removed_steps >= 3  # 至少移除 3 个冗余步骤

        print("\n✅ 场景测试通过!")
        return optimized, stats

    def test_performance_large_macro(self):
        """测试大型宏脚本的性能"""
        print("\n" + "=" * 60)
        print("性能测试: 大型宏脚本（100步骤）")
        print("=" * 60)

        import time

        # 生成大型宏脚本
        large_macro = []
        for i in range(100):
            if i % 3 == 0:
                large_macro.append({
                    "step_number": i + 1,
                    "type": "action",
                    "event_type": "tap",
                    "payload": {"x": 0.5, "y": 0.5}
                })
            elif i % 3 == 1:
                large_macro.append({
                    "step_number": i + 1,
                    "type": "action",
                    "event_type": "wait",
                    "payload": {"duration_ms": 100 + (i % 5) * 50}
                })
            else:
                large_macro.append({
                    "step_number": i + 1,
                    "type": "action",
                    "event_type": "mouse_move",
                    "payload": {"x": 0.1 * (i % 10), "y": 0.1 * (i % 10)}
                })

        optimizer = MacroOptimizer()

        start_time = time.time()
        optimized, stats = optimizer.optimize(large_macro)
        elapsed = time.time() - start_time

        print(f"处理 {len(large_macro)} 步骤耗时: {elapsed*1000:.2f}ms")
        print(f"优化后: {stats.optimized_steps} 步骤")
        print(f"减少: {stats.reduction_ratio:.1%}")

        # 性能要求：100步骤在 100ms 内完成
        assert elapsed < 0.1, f"优化耗时过长: {elapsed*1000:.2f}ms"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
