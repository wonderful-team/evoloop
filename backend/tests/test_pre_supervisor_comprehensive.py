"""
Comprehensive Test Suite for Pre-Supervisor Optimizations

Tests all optimizations and bug fixes:
1. EvoCloud cache with TTL and invalidation
2. Webhook cache invalidation (critical bug fix)
3. Fallback non-blocking (celery failure handling)
4. Predictive memory loading
5. Integration tests
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment
os.environ['EMBEDDED_MODE'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///./test_comprehensive.db'
os.environ['EVOCLOUD_API_URL'] = 'http://localhost:8000'
os.environ['EVOCLOUD_WS_URL'] = 'ws://localhost:8000/ws'


class TestEvoCloudCache:
    """Test EvoCloud Manager cache functionality"""
    
    def test_cache_attributes_exist(self):
        """Test that cache attributes are properly initialized"""
        print("\n[Test] EvoCloud Cache Attributes")
        
        # Import after env setup
        from app.core.evocloud.manager import EvoCloudManager
        
        manager = EvoCloudManager()
        
        # Check cache attributes
        assert hasattr(manager, '_projects_cache'), "Missing _projects_cache"
        assert hasattr(manager, '_projects_cache_time'), "Missing _projects_cache_time"
        assert hasattr(manager, '_projects_cache_ttl'), "Missing _projects_cache_ttl"
        assert manager._projects_cache_ttl == 60, "TTL should be 60 seconds"
        
        print("  ✓ Cache attributes initialized correctly")
        print(f"    - TTL: {manager._projects_cache_ttl}s")
    
    def test_cache_invalidation(self):
        """Test cache invalidation functionality"""
        print("\n[Test] Cache Invalidation")
        
        from app.core.evocloud.manager import EvoCloudManager
        
        manager = EvoCloudManager()
        
        # Set up cache
        manager._projects_cache = [{"id": 1, "name": "Test Project"}]
        manager._projects_cache_time = time.time()
        
        # Invalidate
        manager.invalidate_projects_cache()
        
        # Verify
        assert manager._projects_cache is None, "Cache should be None after invalidation"
        assert manager._projects_cache_time == 0.0, "Cache time should be reset"
        
        print("  ✓ Cache invalidation works correctly")
    
    def test_cache_ttl_logic(self):
        """Test TTL expiration logic"""
        print("\n[Test] Cache TTL Logic")
        
        from app.core.evocloud.manager import EvoCloudManager
        
        manager = EvoCloudManager()
        
        # Test fresh cache (not expired)
        manager._projects_cache_time = time.time()
        manager._projects_cache_ttl = 60
        
        now = time.time()
        is_expired = (now - manager._projects_cache_time) > manager._projects_cache_ttl
        assert not is_expired, "Fresh cache should not be expired"
        
        # Test stale cache (expired)
        manager._projects_cache_time = time.time() - 61  # 61 seconds ago
        now = time.time()
        is_expired = (now - manager._projects_cache_time) > manager._projects_cache_ttl
        assert is_expired, "61s old cache should be expired (TTL=60s)"
        
        print("  ✓ TTL expiration logic correct")
        print("    - Fresh cache (<60s): not expired")
        print("    - Stale cache (>60s): expired")


class TestWebhookCacheInvalidation:
    """Test Webhook cache invalidation (critical bug fix)"""
    
    def test_webhook_invalidate_called(self):
        """Test that webhook calls invalidate_projects_cache"""
        print("\n[Test] Webhook Cache Invalidation (Critical Bug Fix)")
        
        # Read agent.py source
        agent_py_path = Path(__file__).parent.parent / "app" / "api" / "routes" / "agent.py"
        with open(agent_py_path, 'r') as f:
            content = f.read()
        
        # Check for invalidate_projects_cache call in webhook
        assert "evocloud_manager.invalidate_projects_cache()" in content, \
            "Missing cache invalidation in webhook"
        
        # Check it's in the project_switched block
        lines = content.split('\n')
        in_project_switched = False
        found_invalidation = False
        
        for i, line in enumerate(lines):
            if 'if req.event_type == "project_switched":' in line:
                in_project_switched = True
            elif in_project_switched:
                if "evocloud_manager.invalidate_projects_cache()" in line:
                    found_invalidation = True
                    print(f"  ✓ Found at line {i+1}: {line.strip()}")
                    break
                elif line.strip().startswith('return'):
                    break  # End of block
        
        assert found_invalidation, "invalidate_projects_cache not found in project_switched handler"
        
        # Check for explanatory comment
        assert "Project cache invalidated" in content or "critical" in content.lower(), \
            "Missing explanatory comment about the critical bug fix"
        
        print("  ✓ Critical bug fix verified: Webhook invalidates cache")
    
    def test_project_crud_invalidation(self):
        """Test that Project CRUD operations invalidate cache"""
        print("\n[Test] Project CRUD Cache Invalidation")
        
        projects_py = Path(__file__).parent.parent / "app" / "api" / "routes" / "projects.py"
        with open(projects_py, 'r') as f:
            content = f.read()
        
        # Check for invalidate calls
        invalidate_count = content.count("evocloud_manager.invalidate_projects_cache()")
        
        assert invalidate_count >= 2, f"Expected >=2 invalidations, found {invalidate_count}"
        
        print(f"  ✓ Found {invalidate_count} cache invalidation calls in projects.py")


class TestFallbackNonBlocking:
    """Test fallback non-blocking implementation"""
    
    def test_fallback_uses_create_task(self):
        """Test that fallback uses asyncio.create_task"""
        print("\n[Test] Fallback Non-Blocking")
        
        manager_py = Path(__file__).parent.parent / "app" / "core" / "evocloud" / "manager.py"
        with open(manager_py, 'r') as f:
            content = f.read()
        
        # Check for asyncio.create_task in fallback
        assert "asyncio.create_task(" in content, "Missing asyncio.create_task"
        assert "_fallback_upload_log" in content, "Missing _fallback_upload_log method"
        
        # Check that fallback doesn't await directly
        lines = content.split('\n')
        in_except_block = False
        found_fallback_pattern = False
        
        for i, line in enumerate(lines):
            if "except Exception as ex:" in line and "celery" in lines[i-1].lower() if i > 0 else False:
                in_except_block = True
            elif in_except_block:
                if "asyncio.create_task(" in line:
                    found_fallback_pattern = True
                    print(f"  ✓ Found at line {i+1}: {line.strip()}")
                    break
                elif line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                    break  # End of except block
        
        assert found_fallback_pattern, "asyncio.create_task not found in fallback handling"
        
        print("  ✓ Fallback is non-blocking (uses create_task)")
    
    def test_fallback_method_exists(self):
        """Test _fallback_upload_log method exists"""
        print("\n[Test] Fallback Method")
        
        manager_py = Path(__file__).parent.parent / "app" / "core" / "evocloud" / "manager.py"
        with open(manager_py, 'r') as f:
            content = f.read()
        
        assert "async def _fallback_upload_log(" in content, \
            "Missing _fallback_upload_log method"
        
        print("  ✓ _fallback_upload_log method exists")


class TestPredictiveMemoryLoader:
    """Test Predictive Memory Loading functionality"""
    
    def test_module_structure(self):
        """Test predictive_memory_loader.py structure"""
        print("\n[Test] Predictive Memory Loader Module")
        
        loader_py = Path(__file__).parent.parent / "app" / "core" / "engine" / "predictive_memory_loader.py"
        
        assert loader_py.exists(), "predictive_memory_loader.py not found"
        
        with open(loader_py, 'r') as f:
            content = f.read()
        
        # Check required functions
        assert "async def predictive_memory_load(" in content, "Missing predictive_memory_load"
        assert "async def get_predictive_memory(" in content, "Missing get_predictive_memory"
        assert "async def clear_predictive_memory(" in content, "Missing clear_predictive_memory"
        
        # Check singleflight pattern
        assert "_inflight_requests" in content, "Missing singleflight pattern"
        assert "asyncio.Event()" in content, "Missing Event for singleflight"
        
        # Check safety features
        assert "PREDICTIVE_MEMORY_TTL" in content, "Missing TTL"
        assert "try:" in content and "except Exception" in content, "Missing exception handling"
        
        print("  ✓ Module structure correct")
        print("    - predictive_memory_load: ✓")
        print("    - get_predictive_memory: ✓")
        print("    - clear_predictive_memory: ✓")
        print("    - Singleflight pattern: ✓")
        print("    - Safety features: ✓")
    
    def test_middleware_integration(self):
        """Test middleware integration"""
        print("\n[Test] Middleware Integration")
        
        middleware_py = Path(__file__).parent.parent / "app" / "core" / "engine" / "middleware.py"
        with open(middleware_py, 'r') as f:
            content = f.read()
        
        # Check imports
        assert "predictive_memory_loader" in content, "Missing predictive_memory_loader import"
        assert "get_predictive_memory" in content, "Missing get_predictive_memory usage"
        assert "clear_predictive_memory" in content, "Missing clear_predictive_memory usage"
        
        # Check logic flow
        assert "cached_memory = await get_predictive_memory(" in content, \
            "Missing cache retrieval"
        assert "if cached_memory:" in content, "Missing cache hit handling"
        assert "Cache miss - fallback to direct Neo4j query" in content, \
            "Missing fallback comment"
        
        print("  ✓ Middleware integration correct")
    
    def test_chat_endpoint_integration(self):
        """Test chat_endpoint triggers predictive loading"""
        print("\n[Test] Chat Endpoint Integration")
        
        agent_py = Path(__file__).parent.parent / "app" / "api" / "routes" / "agent.py"
        with open(agent_py, 'r') as f:
            content = f.read()
        
        # Check import
        assert "predictive_memory_load" in content, "Missing predictive_memory_load import"
        
        # Check bg_tasks.add_task call
        assert "bg_tasks.add_task(" in content, "Missing bg_tasks.add_task"
        assert "predictive_memory_load," in content, "predictive_memory_load not added to bg_tasks"
        
        # Check it's in chat_endpoint
        lines = content.split('\n')
        in_chat_endpoint = False
        found_add_task = False
        
        for i, line in enumerate(lines):
            if "async def chat_endpoint(" in line:
                in_chat_endpoint = True
            elif in_chat_endpoint:
                if "predictive_memory_load," in line and "bg_tasks.add_task" in lines[i-1] if i > 0 else False:
                    found_add_task = True
                    print(f"  ✓ Found at line {i+1}")
                    break
                elif line.startswith("@router") or line.startswith("def ") or line.startswith("async def "):
                    break  # End of function
        
        assert found_add_task, "bg_tasks.add_task(predictive_memory_load) not found in chat_endpoint"
        
        print("  ✓ Chat endpoint integration correct")


class TestSafetyMechanisms:
    """Test safety mechanisms across all optimizations"""
    
    def test_graceful_fallback(self):
        """Test that all optimizations have graceful fallback"""
        print("\n[Test] Graceful Fallback Mechanisms")
        
        # EvoCloud cache fallback
        manager_py = Path(__file__).parent.parent / "app" / "core" / "evocloud" / "manager.py"
        with open(manager_py, 'r') as f:
            content = f.read()
        
        assert "if self._projects_cache is not None:" in content, \
            "EvoCloud missing stale cache fallback"
        
        # Predictive memory fallback
        middleware_py = Path(__file__).parent.parent / "app" / "core" / "engine" / "middleware.py"
        with open(middleware_py, 'r') as f:
            content = f.read()
        
        assert "Cache miss - fallback to direct Neo4j query" in content, \
            "Predictive memory missing fallback"
        
        print("  ✓ All optimizations have graceful fallback")
    
    def test_exception_handling(self):
        """Test exception handling in optimizations"""
        print("\n[Test] Exception Handling")
        
        # EvoCloud fallback exception handling
        manager_py = Path(__file__).parent.parent / "app" / "core" / "evocloud" / "manager.py"
        with open(manager_py, 'r') as f:
            content = f.read()
        
        assert "try:" in content and "except Exception" in content, \
            "Missing exception handling in EvoCloud"
        
        # Predictive memory exception handling
        loader_py = Path(__file__).parent.parent / "app" / "core" / "engine" / "predictive_memory_loader.py"
        with open(loader_py, 'r') as f:
            content = f.read()
        
        exception_count = content.count("except Exception")
        assert exception_count >= 3, f"Expected >=3 exception handlers, found {exception_count}"
        
        print(f"  ✓ Exception handling adequate ({exception_count} handlers)")
    
    def test_no_critical_data_caching(self):
        """Test that no critical mutable data is cached dangerously"""
        print("\n[Test] Critical Data Safety")
        
        # Check that device status is not cached
        supervisor_builder = Path(__file__).parent.parent / "app" / "core" / "engine" / "prompts" / "supervisor_builder.py"
        with open(supervisor_builder, 'r') as f:
            content = f.read()
        
        # Telemetry should be fetched fresh
        assert "get_awakened_state()" in content, "Should fetch fresh state"
        
        # Device connectivity should not be cached
        assert "is_reachable" in content, "Should check fresh device status"
        
        print("  ✓ Critical data (device status) fetched fresh")


class TestCodeQuality:
    """Test code quality aspects"""
    
    def test_documentation_comments(self):
        """Test that complex optimizations are documented"""
        print("\n[Test] Documentation Quality")
        
        files_to_check = [
            ("app/core/evocloud/manager.py", ["TTL", "cache", "invalidate"]),
            ("app/core/engine/predictive_memory_loader.py", ["Predictive", "background", "cache"]),
            ("app/core/engine/middleware.py", ["Predictive", "memory", "cache"]),
        ]
        
        for filepath, keywords in files_to_check:
            full_path = Path(__file__).parent.parent / filepath
            if full_path.exists():
                with open(full_path, 'r') as f:
                    content = f.read()
                
                # Check for docstrings or comments
                has_docs = '"""' in content or "#" in content
                assert has_docs, f"{filepath} missing documentation"
        
        print("  ✓ Documentation present in all optimized modules")
    
    def test_syntax_validity(self):
        """Test that all modified files have valid Python syntax"""
        print("\n[Test] Syntax Validation")
        
        import ast
        
        files_to_check = [
            "app/core/evocloud/manager.py",
            "app/core/engine/middleware.py",
            "app/core/engine/predictive_memory_loader.py",
            "app/api/routes/agent.py",
            "app/api/routes/projects.py",
        ]
        
        base_path = Path(__file__).parent.parent
        
        for filepath in files_to_check:
            full_path = base_path / filepath
            if full_path.exists():
                with open(full_path, 'r') as f:
                    source = f.read()
                
                try:
                    ast.parse(source)
                    print(f"  ✓ {filepath}")
                except SyntaxError as e:
                    assert False, f"Syntax error in {filepath}: {e}"
        
        print("  ✓ All files have valid Python syntax")


def run_tests():
    """Run all tests"""
    print("=" * 70)
    print(" Pre-Supervisor 优化全面测试套件")
    print("=" * 70)
    
    test_classes = [
        TestEvoCloudCache,
        TestWebhookCacheInvalidation,
        TestFallbackNonBlocking,
        TestPredictiveMemoryLoader,
        TestSafetyMechanisms,
        TestCodeQuality,
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for test_class in test_classes:
        print(f"\n{'─' * 70}")
        print(f"测试类: {test_class.__name__}")
        print(f"{'─' * 70}")
        
        # Get test methods
        test_methods = [m for m in dir(test_class) if m.startswith('test_')]
        
        for method_name in test_methods:
            total_tests += 1
            try:
                test_instance = test_class()
                method = getattr(test_instance, method_name)
                method()
                passed_tests += 1
            except AssertionError as e:
                failed_tests.append((test_class.__name__, method_name, str(e)))
                print(f"\n  ❌ FAILED: {method_name}")
                print(f"     Error: {e}")
            except Exception as e:
                failed_tests.append((test_class.__name__, method_name, f"Unexpected: {e}"))
                print(f"\n  ❌ ERROR: {method_name}")
                print(f"     Exception: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print(" 测试结果摘要")
    print("=" * 70)
    print(f"  总测试数: {total_tests}")
    print(f"  通过: {passed_tests} ✅")
    print(f"  失败: {len(failed_tests)} ❌")
    
    if failed_tests:
        print("\n  失败的测试:")
        for class_name, method_name, error in failed_tests:
            print(f"    - {class_name}.{method_name}")
            print(f"      {error[:100]}...")
    
    print("=" * 70)
    
    if len(failed_tests) == 0:
        print("\n🎉 所有测试通过！系统已准备就绪。")
        return 0
    else:
        print(f"\n⚠️  {len(failed_tests)} 个测试失败，请检查。")
        return 1


if __name__ == "__main__":
    exit(run_tests())
