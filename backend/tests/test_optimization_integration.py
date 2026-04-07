"""
Integration and Performance Tests for All Optimizations

Run with: pytest tests/test_optimization_integration.py -v
"""

import asyncio
import time
from dataclasses import dataclass
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

import sys
from types import ModuleType

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')


# ============================================================================
# Integration Test Scenarios
# ============================================================================

class TestToolCacheIntegration:
    """Integration tests for Tool Cache with realistic scenarios."""
    
    @pytest.fixture
    def mock_tool_execution(self):
        """Create a mock tool that tracks execution count."""
        execution_count = 0
        
        async def execute():
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.05)  # Simulate 50ms IO
            return {"content": f"Result #{execution_count}", "executions": execution_count}
        
        return execute, lambda: execution_count
    
    @pytest.mark.asyncio
    async def test_worker_repeated_reads_scenario(self, mock_tool_execution):
        """
        Scenario: Worker reads file, analyzes, reads again to verify.
        Without cache: 2 reads = 100ms
        With cache: 1 read = 50ms
        """
        from app.core.tools.cache import DeterministicToolCache
        
        execute_fn, get_count = mock_tool_execution
        cache = DeterministicToolCache()
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="stable_hash")):
            # Step 1: Initial read
            result1, meta1 = await cache.execute(
                'read_file', 
                {'path': '/workspace/src/app.py'}, 
                execute_fn
            )
            assert meta1['cached'] is False
            
            # Step 2: Analysis (simulated by sleep)
            await asyncio.sleep(0.01)
            
            # Step 3: Re-read for verification
            result2, meta2 = await cache.execute(
                'read_file',
                {'path': '/workspace/src/app.py'},
                execute_fn
            )
            assert meta2['cached'] is True
            
            # Should only execute once
            assert get_count() == 1
            assert result1 == result2
    
    @pytest.mark.asyncio
    async def test_parallel_subtasks_read_same_file(self):
        """
        Scenario: 3 parallel subtasks all need to read config.json.
        Without cache: 3 reads = 150ms
        With cache: 1 read = 50ms (concurrent safety)
        """
        from app.core.tools.cache import DeterministicToolCache
        
        cache = DeterministicToolCache()
        execution_count = 0
        
        async def execute():
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.05)
            return {"config": "value"}
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="config_hash")):
            # Launch 3 concurrent reads
            tasks = [
                cache.execute('read_file', {'path': '/workspace/config.json'}, execute)
                for _ in range(3)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Should only execute once
            assert execution_count == 1
            assert all(r[0] == {"config": "value"} for r in results)


class TestContextCacheIntegration:
    """Integration tests for Context Cache with realistic scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_request_flow(self):
        """
        Scenario: Full request with Supervisor -> Worker -> Finish.
        Context should be cached and reused.
        """
        from app.core.context.cache import LayeredContextCache
        
        # Clear cache
        LayeredContextCache._static_cache.clear()
        
        load_count = 0
        async def mock_loader():
            nonlocal load_count
            load_count += 1
            await asyncio.sleep(0.1)  # Simulate DB load
            return {
                'project_concepts': 'Test Project',
                'active_skills': ['skill1', 'skill2'],
                'telemetry': {'android': []},
            }
        
        # Node 1: Supervisor
        t0 = time.time()
        static1 = await LayeredContextCache.get_static_layer("req123", 1, mock_loader)
        t1 = time.time()
        
        # Node 2: Worker (same request)
        static2 = await LayeredContextCache.get_static_layer("req123", 1, mock_loader)
        t2 = time.time()
        
        # Node 3: Finish (same request)
        static3 = await LayeredContextCache.get_static_layer("req123", 1, mock_loader)
        t3 = time.time()
        
        # Only loaded once
        assert load_count == 1
        
        # First call took full time
        assert (t1 - t0) >= 0.1
        
        # Subsequent calls were fast (< 1ms)
        assert (t2 - t1) < 0.01
        assert (t3 - t2) < 0.01
        
        # Data consistency
        assert static1.project_concepts == static2.project_concepts == static3.project_concepts
    
    def test_dynamic_state_isolation(self):
        """
        Scenario: Multiple nodes should get fresh blackboard copies.
        """
        from app.core.context.cache import LayeredContextCache
        
        # Simulate state changes
        state = {
            "blackboard": {"counter": 0},
            "execution_ticket": {"step": 1},
            "messages": [],
        }
        
        # Get dynamic layer for "Supervisor"
        dynamic1 = LayeredContextCache.get_dynamic_layer(state)
        dynamic1.blackboard["counter"] = 1  # Modify
        
        # Get dynamic layer for "Worker" (same state object)
        dynamic2 = LayeredContextCache.get_dynamic_layer(state)
        
        # Should see original value, not the modified one
        assert dynamic2.blackboard["counter"] == 0


class TestFinishAuditorIntegration:
    """Integration tests for Finish Auditor with realistic scenarios."""
    
    def test_simple_query_readonly(self):
        """
        Scenario: User asks "What files are in the project?"
        Should use minimal audit.
        """
        from app.core.engine.nodes.finish import LayeredAuditor
        
        auditor = LayeredAuditor()
        
        tool_history = [
            'list_directory:{"path": "/workspace"}',
            'read_file:{"path": "/workspace/README.md"}',
        ]
        messages = [
            MockMessage(tool_calls=[{'name': 'list_directory'}]),
            MockMessage(content="Files: src/, tests/, README.md"),
        ]
        blackboard = {}
        state = {}
        
        decision = auditor.classify_tier(tool_history, messages, blackboard, state)
        
        assert decision.tier == "minimal"
    
    def test_code_edit_requires_comprehensive(self):
        """
        Scenario: Worker edits a file.
        Must use comprehensive audit.
        """
        from app.core.engine.nodes.finish import LayeredAuditor
        
        auditor = LayeredAuditor()
        
        tool_history = [
            'read_file:{"path": "/workspace/app.py"}',
            'edit_file:{"path": "/workspace/app.py", "target": "old", "replacement": "new"}',
        ]
        messages = [
            MockMessage(content="Fixed the bug"),
        ]
        blackboard = {}
        state = {}
        
        decision = auditor.classify_tier(tool_history, messages, blackboard, state)
        
        assert decision.tier == "comprehensive"
        assert "file_modification" in decision.reason
    
    def test_error_in_output_requires_comprehensive(self):
        """
        Scenario: Worker encountered an error.
        Must use comprehensive audit.
        """
        from app.core.engine.nodes.finish import LayeredAuditor
        
        auditor = LayeredAuditor()
        
        tool_history = ['execute_command:{"cmd": "python test.py"}']
        messages = [
            MockMessage(content="[ERROR: Command failed with exit code 1]"),
        ]
        blackboard = {}
        state = {}
        
        decision = auditor.classify_tier(tool_history, messages, blackboard, state)
        
        assert decision.tier == "comprehensive"


# ============================================================================
# Performance Benchmarks
# ============================================================================

class TestPerformanceBenchmarks:
    """Performance benchmark tests."""
    
    @pytest.mark.benchmark
    @pytest.mark.asyncio
    async def test_tool_cache_hit_performance(self):
        """
        Benchmark: Tool cache hit should be < 1ms.
        """
        from app.core.tools.cache import DeterministicToolCache
        
        cache = DeterministicToolCache()
        
        async def execute():
            return {"data": "x" * 1000}
        
        with patch.object(cache, '_compute_file_hash', AsyncMock(return_value="hash")):
            # Warm up
            await cache.execute('read_file', {'path': '/tmp/test'}, execute)
            
            # Benchmark 1000 cache hits
            start = time.time()
            for _ in range(1000):
                await cache.execute('read_file', {'path': '/tmp/test'}, execute)
            duration = (time.time() - start) / 1000 * 1000  # ms per op
            
            assert duration < 1.0, f"Cache hit too slow: {duration:.2f}ms"
            print(f"\n  Cache hit latency: {duration:.3f}ms")
    
    @pytest.mark.benchmark
    def test_context_classification_performance(self):
        """
        Benchmark: Audit classification should be < 0.1ms.
        """
        from app.core.engine.nodes.finish import LayeredAuditor
        
        auditor = LayeredAuditor()
        
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="File content")]
        blackboard = {}
        state = {}
        
        # Benchmark 10000 classifications
        start = time.time()
        for _ in range(10000):
            auditor.classify_tier(tool_history, messages, blackboard, state)
        duration = (time.time() - start) / 10000 * 1000000  # microseconds per op
        
        assert duration < 100, f"Classification too slow: {duration:.1f}μs"
        print(f"\n  Classification latency: {duration:.1f}μs")
    
    @pytest.mark.benchmark
    @pytest.mark.asyncio
    async def test_minimal_audit_performance(self):
        """
        Benchmark: Minimal audit should be < 1ms.
        """
        from app.core.engine.nodes.finish import LayeredAuditor
        
        auditor = LayeredAuditor()
        messages = [
            MockMessage(tool_calls=[{'name': 'read_file'}]),
            MockMessage(content="File content here"),
        ]
        
        # Benchmark 1000 minimal audits
        start = time.time()
        for _ in range(1000):
            await auditor.audit_minimal(messages, {})
        duration = (time.time() - start) / 1000 * 1000  # ms per op
        
        assert duration < 1.0, f"Minimal audit too slow: {duration:.2f}ms"
        print(f"\n  Minimal audit latency: {duration:.3f}ms")


# ============================================================================
# End-to-End Scenarios
# ============================================================================

class TestEndToEndScenarios:
    """Complete end-to-end scenarios."""
    
    @pytest.mark.asyncio
    async def test_scenario_simple_file_read(self):
        """
        End-to-end: User asks "Read app.py and tell me what it does"
        """
        print("\n  [Scenario] Simple file read query")
        
        # Track metrics
        metrics = {
            'tool_executions': 0,
            'context_loads': 0,
            'audit_tier': None,
        }
        
        # Simulate Tool Cache
        async def mock_tool_execute():
            metrics['tool_executions'] += 1
            await asyncio.sleep(0.05)
            return "def main(): pass"
        
        # Simulate Context Cache
        async def mock_context_loader():
            metrics['context_loads'] += 1
            await asyncio.sleep(0.1)
            return {'concepts': 'Test'}
        
        # Step 1: Tool execution (with cache)
        from app.core.tools.cache import DeterministicToolCache
        tool_cache = DeterministicToolCache()
        
        with patch.object(tool_cache, '_compute_file_hash', AsyncMock(return_value="hash")):
            result1, _ = await tool_cache.execute('read_file', {'path': 'app.py'}, mock_tool_execute)
            result2, meta2 = await tool_cache.execute('read_file', {'path': 'app.py'}, mock_tool_execute)
        
        assert meta2['cached'] is True
        assert metrics['tool_executions'] == 1  # Only executed once
        
        # Step 2: Context hydration
        from app.core.context.cache import LayeredContextCache
        LayeredContextCache._static_cache.clear()
        
        static1 = await LayeredContextCache.get_static_layer("req1", 1, mock_context_loader)
        static2 = await LayeredContextCache.get_static_layer("req1", 1, mock_context_loader)
        
        assert metrics['context_loads'] == 1  # Only loaded once
        
        # Step 3: Audit classification
        from app.core.engine.nodes.finish import LayeredAuditor
        auditor = LayeredAuditor()
        
        decision = auditor.classify_tier(
            tool_history=['read_file:{"path": "app.py"}'],
            messages=[MockMessage(content="The file contains a main function")],
            blackboard={},
            state={}
        )
        
        assert decision.tier == "minimal"
        
        print(f"    Tool executions: {metrics['tool_executions']} (expected: 1)")
        print(f"    Context loads: {metrics['context_loads']} (expected: 1)")
        print(f"    Audit tier: {decision.tier} (expected: minimal)")
    
    @pytest.mark.asyncio
    async def test_scenario_code_modification(self):
        """
        End-to-end: User asks "Fix the bug in app.py"
        """
        print("\n  [Scenario] Code modification with error")
        
        # This should trigger comprehensive audit
        from app.core.engine.nodes.finish import LayeredAuditor
        
        auditor = LayeredAuditor()
        
        decision = auditor.classify_tier(
            tool_history=[
                'read_file:{"path": "app.py"}',
                'edit_file:{"path": "app.py", "target": "bug", "replacement": "fix"}',
            ],
            messages=[MockMessage(content="Fixed the bug but got error: [ERROR: Test failed]")],
            blackboard={},
            state={}
        )
        
        assert decision.tier == "comprehensive"
        assert "file_modification" in decision.reason
        assert "error_detected" in decision.reason
        
        print(f"    Audit tier: {decision.tier} (expected: comprehensive)")
        print(f"    Triggers: {decision.reason}")


# ============================================================================
# Mock Helpers
# ============================================================================

class MockMessage:
    """Mock message for testing."""
    def __init__(self, content=None, tool_calls=None, msg_type="ai"):
        self.content = content
        self.tool_calls = tool_calls or []
        self.type = msg_type


# ============================================================================
# Run All Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
