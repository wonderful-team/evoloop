"""
宏脚本优化器 (MacroOptimizer)

借鉴视频关键帧提取逻辑，对宏脚本进行冗余去除和优化。

核心功能:
- 合并相邻的 wait 步骤
- 去除重复操作
- 时间间隔优化
- 无效操作过滤
- 智能步骤重排序

优化策略类似于 KeyframeSelector:
- 跳过冗余: 忽略高频低价值操作
- 时间窗口去重: 过于接近的步骤合并
- 优先级筛选: 保留高价值操作
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class OptimizationStrategy(Enum):
    """优化策略类型"""
    MERGE_WAITS = "merge_waits"           # 合并相邻等待
    REMOVE_DUPLICATES = "remove_duplicates"  # 去除重复操作
    TIME_INTERVAL = "time_interval"       # 时间间隔优化
    FILTER_REDUNDANT = "filter_redundant" # 过滤冗余操作
    COALESCE_EXTRACTS = "coalesce_extracts"  # 合并提取操作


@dataclass
class OptimizationResult:
    """优化结果"""
    original_steps: int
    optimized_steps: int
    removed_steps: int
    merged_steps: int
    time_saved_ms: int
    strategies_applied: List[str] = field(default_factory=list)

    @property
    def reduction_ratio(self) -> float:
        """步骤减少比例"""
        if self.original_steps == 0:
            return 0.0
        return (self.original_steps - self.optimized_steps) / self.original_steps

    def __str__(self) -> str:
        return (f"MacroOptimizer: {self.original_steps} -> {self.optimized_steps} steps "
                f"(-{self.reduction_ratio:.1%}, saved {self.time_saved_ms}ms)")


class MacroOptimizer:
    """
    宏脚本优化器

    类似于视频关键帧选择器，但针对宏脚本步骤进行优化。
    """

    # 配置参数（类似于 KeyframeSelector）
    MIN_STEP_INTERVAL_MS = 300          # 最小步骤间隔（避免过快操作）
    MIN_WAIT_DURATION_MS = 100          # 最小有效等待时间
    MAX_WAIT_DURATION_MS = 5000         # 最大等待时间（超过则截断）
    DUPLICATE_DETECTION_WINDOW = 3      # 重复检测窗口大小

    # 冗余操作类型（可跳过或合并）
    REDUNDANT_ACTIONS = {'wait', 'sleep'}
    LOW_VALUE_ACTIONS = {'mouse_move', 'cursor_move', 'hover'}

    def __init__(self,
                 min_interval_ms: int = None,
                 enable_all_strategies: bool = True):
        """
        初始化优化器

        Args:
            min_interval_ms: 最小步骤间隔（毫秒）
            enable_all_strategies: 是否启用所有优化策略
        """
        self.min_interval_ms = min_interval_ms or self.MIN_STEP_INTERVAL_MS
        self.strategies_enabled = {
            OptimizationStrategy.MERGE_WAITS: True,
            OptimizationStrategy.REMOVE_DUPLICATES: True,
            OptimizationStrategy.TIME_INTERVAL: True,
            OptimizationStrategy.FILTER_REDUNDANT: True,
            OptimizationStrategy.COALESCE_EXTRACTS: enable_all_strategies,
        }

    def optimize(self, macro_script: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], OptimizationResult]:
        """
        优化宏脚本

        Args:
            macro_script: 原始宏脚本步骤列表

        Returns:
            (优化后的脚本, 优化结果统计)
        """
        if not macro_script:
            return [], OptimizationResult(0, 0, 0, 0, 0)

        original_count = len(macro_script)
        logger.info(f"[MacroOptimizer] Starting optimization: {original_count} steps")

        # 统计信息
        stats = {
            'removed': 0,
            'merged': 0,
            'time_saved': 0,
            'strategies': []
        }

        # 第1轮: 过滤低价值操作（类似于跳过 mouse_move）
        if self.strategies_enabled[OptimizationStrategy.FILTER_REDUNDANT]:
            filtered = self._filter_redundant_actions(macro_script)
            stats['removed'] += len(macro_script) - len(filtered)
            if len(filtered) < len(macro_script):
                stats['strategies'].append('filter_redundant')
                logger.debug(f"[MacroOptimizer] Filtered {len(macro_script) - len(filtered)} redundant actions")
        else:
            filtered = macro_script

        # 第2轮: 合并相邻 wait 步骤
        if self.strategies_enabled[OptimizationStrategy.MERGE_WAITS]:
            merged_waits, merge_count, time_saved = self._merge_wait_steps(filtered)
            stats['merged'] += merge_count
            stats['time_saved'] += time_saved
            if merge_count > 0:
                stats['strategies'].append('merge_waits')
                logger.debug(f"[MacroOptimizer] Merged {merge_count} wait steps, saved {time_saved}ms")
        else:
            merged_waits = filtered

        # 第3轮: 去除重复操作
        if self.strategies_enabled[OptimizationStrategy.REMOVE_DUPLICATES]:
            deduped, dup_count = self._remove_duplicate_actions(merged_waits)
            stats['removed'] += dup_count
            if dup_count > 0:
                stats['strategies'].append('remove_duplicates')
                logger.debug(f"[MacroOptimizer] Removed {dup_count} duplicate actions")
        else:
            deduped = merged_waits

        # 第4轮: 时间间隔优化
        if self.strategies_enabled[OptimizationStrategy.TIME_INTERVAL]:
            time_optimized, time_saved = self._optimize_time_intervals(deduped)
            stats['time_saved'] += time_saved
            if time_saved > 0:
                stats['strategies'].append('time_interval')
                logger.debug(f"[MacroOptimizer] Time optimization saved {time_saved}ms")
        else:
            time_optimized = deduped

        # 第5轮: 合并提取操作（高级优化）
        if self.strategies_enabled[OptimizationStrategy.COALESCE_EXTRACTS]:
            coalesced, coalesce_count = self._coalesce_extract_operations(time_optimized)
            if coalesce_count > 0:
                stats['strategies'].append('coalesce_extracts')
                logger.debug(f"[MacroOptimizer] Coalesced {coalesce_count} extract operations")
        else:
            coalesced = time_optimized

        # 重新编号步骤
        optimized = self._renumber_steps(coalesced)

        # 构建结果
        result = OptimizationResult(
            original_steps=original_count,
            optimized_steps=len(optimized),
            removed_steps=stats['removed'],
            merged_steps=stats['merged'],
            time_saved_ms=stats['time_saved'],
            strategies_applied=stats['strategies']
        )

        logger.info(f"[MacroOptimizer] {result}")
        return optimized, result

    def _filter_redundant_actions(self, steps: List[Dict]) -> List[Dict]:
        """
        过滤冗余操作（类似于 KeyframeSelector 跳过 mouse_move）
        """
        filtered = []

        for step in steps:
            event_type = step.get('event_type', '')
            action_type = step.get('type', '')

            # 跳过显式低价值操作
            if event_type in self.LOW_VALUE_ACTIONS:
                logger.debug(f"  Filtered low-value action: {event_type}")
                continue

            # 跳过无效的 wait（时间为0或负数）
            if action_type == 'wait':
                duration = step.get('payload', {}).get('duration_ms', 0)
                if duration <= 0:
                    logger.debug(f"  Filtered invalid wait: {duration}ms")
                    continue

            filtered.append(step)

        return filtered

    def _merge_wait_steps(self, steps: List[Dict]) -> Tuple[List[Dict], int, int]:
        """
        合并相邻的 wait 步骤

        Returns:
            (合并后的步骤列表, 合并次数, 节省的时间ms)
        """
        merged = []
        merge_count = 0
        time_saved = 0

        i = 0
        while i < len(steps):
            step = steps[i]

            # 检查是否是 wait 步骤
            if step.get('type') != 'action' or step.get('event_type') != 'wait':
                merged.append(step)
                i += 1
                continue

            # 查找连续的 wait 步骤
            total_wait = step.get('payload', {}).get('duration_ms', 0)
            consecutive_waits = 1
            j = i + 1

            while j < len(steps):
                next_step = steps[j]
                if (next_step.get('type') == 'action' and
                    next_step.get('event_type') == 'wait'):
                    wait_time = next_step.get('payload', {}).get('duration_ms', 0)
                    total_wait += wait_time
                    consecutive_waits += 1
                    j += 1
                else:
                    break

            # 如果只有一个 wait，检查是否需要延长
            if consecutive_waits == 1:
                if total_wait < self.MIN_WAIT_DURATION_MS:
                    # 太短的 wait 延长到最小值
                    step['payload']['duration_ms'] = self.MIN_WAIT_DURATION_MS
                    time_saved -= (self.MIN_WAIT_DURATION_MS - total_wait)  # 负数表示增加
                elif total_wait > self.MAX_WAIT_DURATION_MS:
                    # 太长的 wait 截断
                    time_saved += (total_wait - self.MAX_WAIT_DURATION_MS)
                    step['payload']['duration_ms'] = self.MAX_WAIT_DURATION_MS
                merged.append(step)
            else:
                # 合并多个 wait
                merged_wait = step.copy()
                # 截断过长的等待
                if total_wait > self.MAX_WAIT_DURATION_MS:
                    time_saved += (total_wait - self.MAX_WAIT_DURATION_MS)
                    total_wait = self.MAX_WAIT_DURATION_MS
                merged_wait['payload']['duration_ms'] = total_wait
                merged.append(merged_wait)
                merge_count += consecutive_waits - 1
                # 合并节省的开销（假设每个步骤有 50ms 的开销）
                time_saved += (consecutive_waits - 1) * 50

            i = j

        return merged, merge_count, time_saved

    def _remove_duplicate_actions(self, steps: List[Dict]) -> Tuple[List[Dict], int]:
        """
        去除重复操作（类似于时间窗口去重）

        检测并移除在短时间内重复执行的相同操作。
        """
        deduped = []
        removed_count = 0

        for i, step in enumerate(steps):
            # 只检查 action 类型
            if step.get('type') != 'action':
                deduped.append(step)
                continue

            # 检查是否是重复操作
            if self._is_duplicate_action(step, deduped[-self.DUPLICATE_DETECTION_WINDOW:]):
                logger.debug(f"  Removed duplicate action at step {i}: {step.get('event_type')}")
                removed_count += 1
                continue

            deduped.append(step)

        return deduped, removed_count

    def _is_duplicate_action(self, step: Dict, previous_steps: List[Dict]) -> bool:
        """
        判断是否是重复操作

        检查操作类型、目标选择器和关键参数是否都相同。
        只有所有关键字段都相同时，才认为是重复操作。
        """
        if not previous_steps:
            return False

        current_type = step.get('event_type')
        current_payload = step.get('payload', {})
        current_selector = step.get('target_selector')

        for prev in previous_steps:
            if prev.get('type') != 'action':
                continue

            prev_type = prev.get('event_type')
            prev_payload = prev.get('payload', {})
            prev_selector = prev.get('target_selector')

            # 检查操作类型是否相同
            if current_type != prev_type:
                continue

            # 检查目标选择器是否相同（如果存在）
            if current_selector != prev_selector:
                continue

            # 检查坐标是否相同（对于 tap/click/swipe）
            if current_type in ('tap', 'click'):
                coord_match = (abs(current_payload.get('x', 0) - prev_payload.get('x', 0)) < 0.01 and
                              abs(current_payload.get('y', 0) - prev_payload.get('y', 0)) < 0.01)
                if not coord_match:
                    continue
                # 如果坐标相同但 button/modifiers 不同，不是重复
                if current_payload.get('button') != prev_payload.get('button'):
                    continue
                if current_payload.get('modifiers') != prev_payload.get('modifiers'):
                    continue
                return True

            # 检查输入操作（必须文本和其他关键参数都相同）
            if current_type in ('input', 'type_text'):
                if current_payload.get('text') != prev_payload.get('text'):
                    continue
                # 检查其他关键参数
                if current_payload.get('clear_first') != prev_payload.get('clear_first'):
                    continue
                if current_payload.get('delay_ms') != prev_payload.get('delay_ms'):
                    continue
                return True

            # 检查 open_app 是否重复
            if current_type == 'open_app':
                pkg_match = (current_payload.get('package') == prev_payload.get('package') or
                           current_payload.get('app_name') == prev_payload.get('app_name') or
                           current_payload.get('text') == prev_payload.get('text'))
                if pkg_match:
                    return True
                continue

            # 检查 navigate/goto（URL 必须相同）
            if current_type in ('navigate', 'goto'):
                if current_payload.get('url') == prev_payload.get('url'):
                    return True
                continue

            # 对于其他类型：比较完整的 payload（排除 timestamp 等非关键字段）
            def _normalize_payload(payload: Dict) -> Dict:
                """归一化 payload，排除非关键字段"""
                exclude_keys = {'timestamp', 'step_number', 'random_id', 'request_id'}
                return {k: v for k, v in payload.items() if k not in exclude_keys}

            if _normalize_payload(current_payload) == _normalize_payload(prev_payload):
                return True

        return False

    def _optimize_time_intervals(self, steps: List[Dict]) -> Tuple[List[Dict], int]:
        """
        优化时间间隔

        确保步骤之间有足够的执行时间，避免过快操作导致失败。
        """
        optimized = []
        time_saved = 0
        last_timestamp = 0

        for step in steps:
            current_timestamp = step.get('timestamp', 0)

            # 如果步骤间隔太短，添加或延长 wait
            if current_timestamp > 0 and last_timestamp > 0:
                interval = current_timestamp - last_timestamp
                if interval < self.min_interval_ms:
                    # 需要添加等待
                    wait_needed = self.min_interval_ms - interval

                    # 检查上一步是否是 wait
                    if optimized and optimized[-1].get('event_type') == 'wait':
                        # 延长现有 wait
                        old_wait = optimized[-1]['payload'].get('duration_ms', 0)
                        optimized[-1]['payload']['duration_ms'] = old_wait + wait_needed
                    else:
                        # 插入新的 wait
                        wait_step = {
                            'type': 'action',
                            'event_type': 'wait',
                            'source': step.get('source', 'global'),
                            'payload': {'duration_ms': wait_needed},
                            'description': 'Auto-inserted for timing'
                        }
                        optimized.append(wait_step)

                    time_saved -= wait_needed  # 负数表示增加时间

            optimized.append(step)
            if current_timestamp > 0:
                last_timestamp = current_timestamp

        return optimized, time_saved

    def _coalesce_extract_operations(self, steps: List[Dict]) -> Tuple[List[Dict], int]:
        """
        合并提取操作（高级优化）

        如果多个 extract 操作连续出现，考虑合并为一个批量提取。
        """
        coalesced = []
        coalesce_count = 0

        i = 0
        while i < len(steps):
            step = steps[i]

            # 检查是否是 extract 类型
            if step.get('type') != 'extract':
                coalesced.append(step)
                i += 1
                continue

            # 查找连续的 extract 步骤
            extracts = [step]
            j = i + 1

            while j < len(steps) and steps[j].get('type') == 'extract':
                extracts.append(steps[j])
                j += 1

            # 如果只有一个 extract，直接保留
            if len(extracts) == 1:
                coalesced.append(step)
            else:
                # 合并多个 extract
                merged_extract = {
                    'type': 'extract',
                    'source': step.get('source', 'global'),
                    'extract_type': 'batch',
                    'keys': [e.get('key', f'data_{k}') for k, e in enumerate(extracts)],
                    'payload': {
                        'batch': True,
                        'count': len(extracts),
                        'original_steps': [e.get('step_number') for e in extracts]
                    }
                }
                coalesced.append(merged_extract)
                coalesce_count += len(extracts) - 1
                logger.debug(f"  Coalesced {len(extracts)} extract operations into batch")

            i = j

        return coalesced, coalesce_count

    def _renumber_steps(self, steps: List[Dict]) -> List[Dict]:
        """
        重新编号步骤
        """
        for i, step in enumerate(steps, 1):
            step['step_number'] = i
        return steps

    # 便捷方法
    @classmethod
    def quick_optimize(cls, macro_script: List[Dict]) -> List[Dict]:
        """
        快速优化，使用默认配置
        """
        optimizer = cls()
        optimized, _ = optimizer.optimize(macro_script)
        return optimized
