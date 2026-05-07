import platform

def is_macos():
    return platform.system() == "Darwin"

#!/usr/bin/env python3
"""
macOS 速度优化测试套件
分层测试：单元测试 → 集成测试 → 性能基准
"""

import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict, Any
import pytest

# 测试配置
TEST_CONFIG = {
    "wechat_bundle_id": "com.tencent.xinWeChat",
    "chrome_bundle_id": "com.google.Chrome",
    "test_message": "Hello from EvoLoop Test",
}


class TestShortcutMapping:
    """单元测试：快捷键映射"""
    
    def test_wechat_shortcuts(self):
        """测试微信快捷键"""
        from app.core.shortcuts import get_shortcut

        assert get_shortcut(TEST_CONFIG["wechat_bundle_id"], "发送") == "return"
        assert get_shortcut(TEST_CONFIG["wechat_bundle_id"], "search") == "cmd+f"
        assert get_shortcut(TEST_CONFIG["wechat_bundle_id"], "new_chat") == "cmd+n"
        print("✅ WeChat shortcuts test passed")
    
    def test_chrome_shortcuts(self):
        """测试 Chrome 快捷键"""
        from app.core.shortcuts import get_shortcut
        
        assert get_shortcut(TEST_CONFIG["chrome_bundle_id"], "new_tab") == "cmd+t"
        assert get_shortcut(TEST_CONFIG["chrome_bundle_id"], "close_tab") == "cmd+w"
        assert get_shortcut(TEST_CONFIG["chrome_bundle_id"], "address_bar") == "cmd+l"
        print("✅ Chrome shortcuts test passed")
    
    def test_generic_shortcuts(self):
        """测试通用快捷键"""
        from app.core.shortcuts import get_shortcut
        
        # 任何应用都应该有通用快捷键
        assert get_shortcut("any.app.bundle", "复制") == "cmd+c"
        assert get_shortcut("any.app.bundle", "paste") == "cmd+v"
        assert get_shortcut("any.app.bundle", "全选") == "cmd+a"
        print("✅ Generic shortcuts test passed")
    
    def test_unknown_element(self):
        """测试未知元素返回 None"""
        from app.core.shortcuts import get_shortcut
        
        assert get_shortcut(TEST_CONFIG["wechat_bundle_id"], "不存在的按钮") is None
        print("✅ Unknown element returns None")


class TestPerformanceBenchmark:
    """性能基准测试"""
    
    def test_shortcut_lookup_speed(self):
        """测试快捷键查询速度"""
        from app.core.shortcuts import get_shortcut
        
        start = time.time()
        for _ in range(1000):
            get_shortcut(TEST_CONFIG["wechat_bundle_id"], "发送")
        elapsed = time.time() - start
        
        # 1000 次查询应该在 10ms 内
        assert elapsed < 0.01
        print(f"✅ Shortcut lookup: 1000 calls in {elapsed*1000:.2f}ms")
    
class TestIntegration:
    """集成测试：模拟 Agent 调用"""
    
class TestRealEnvironment:
    """真实环境测试（需要 macOS）"""
    
class PerformanceMonitor:
    """性能监控器 - 持续观察"""
    
    def __init__(self, log_file: str = "macos_perf_log.jsonl"):
        self.log_file = log_file
        self.metrics = []
    
    async def record_operation(self, operation: str, details: Dict, duration: float):
        """记录操作性能"""
        metric = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "duration_ms": duration * 1000,
            "details": details,
        }
        
        # 写入日志
        with open(self.log_file, "a") as f:
            f.write(json.dumps(metric) + "\n")
        
        self.metrics.append(metric)
    
    def generate_report(self) -> Dict:
        """生成性能报告"""
        if not self.metrics:
            return {"error": "No metrics collected"}
        
        # 按操作类型分组统计
        from collections import defaultdict
        by_operation = defaultdict(list)
        
        for m in self.metrics:
            by_operation[m["operation"]].append(m["duration_ms"])
        
        report = {}
        for op, durations in by_operation.items():
            report[op] = {
                "count": len(durations),
                "avg_ms": sum(durations) / len(durations),
                "min_ms": min(durations),
                "max_ms": max(durations),
                "p95_ms": sorted(durations)[int(len(durations)*0.95)],
            }
        
        return report


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("🚀 macOS 速度优化测试套件")
    print("=" * 70)
    
    # 单元测试
    print("\n📦 单元测试")
    print("-" * 70)
    
    test_shortcut = TestShortcutMapping()
    test_shortcut.test_wechat_shortcuts()
    test_shortcut.test_chrome_shortcuts()
    test_shortcut.test_generic_shortcuts()
    test_shortcut.test_unknown_element()
    
    # 性能测试
    print("\n⚡ 性能测试")
    print("-" * 70)
    
    test_perf = TestPerformanceBenchmark()
    test_perf.test_shortcut_lookup_speed()
    test_perf.test_batch_planning_speed()
    
    # 集成测试（模拟）
    print("\n🔗 集成测试")
    print("-" * 70)
    
    # 注意：真实集成测试需要完整环境
    print("⚠️  集成测试需要完整后端环境，跳过")
    print("   运行方式: pytest tests/monitoring/test_macos_optimization.py -v")
    
    print("\n" + "=" * 70)
    print("✅ 所有单元测试和性能测试通过")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
