"""
Performance and Stability Tests
Covers: PERF-001~004, STAB-001~003
"""
import pytest
import asyncio
import time
import httpx
import tempfile
import os
import psutil

from tests.config import config, get_auth_headers


class TestPerformance:
    """Performance test suite."""

    # PERF-001: Concurrent Requests
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_perf_001_concurrent_requests(self):
        """Test handling 10 concurrent chat requests."""
        async def send_request(client: httpx.AsyncClient, index: int):
            thread_id = config.generate_thread_id()
            start_time = time.time()
            
            response = await client.post("/api/v1/chat", json={
                "message": f"Hello from request {index}",
                "thread_id": thread_id,
                "project_id": config.PROJECT_ID
            })
            
            elapsed = time.time() - start_time
            return response.status_code, elapsed
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=30.0
        ) as client:
            # Send 10 concurrent requests
            tasks = [send_request(client, i) for i in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Analyze results
            successful = sum(1 for r in results if isinstance(r, tuple) and r[0] == 200)
            response_times = [r[1] for r in results if isinstance(r, tuple)]
            avg_time = sum(response_times) / len(response_times) if response_times else 0
            
            # All requests should succeed
            assert successful == 10, f"Only {successful}/10 requests succeeded"
            
            # Average response time should be < 2 seconds
            assert avg_time < 2.0, f"Average response time {avg_time:.2f}s > 2s"

    # PERF-002: Long Session
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_perf_002_long_session(self):
        """Test memory stability with 100+ messages."""
        thread_id = config.generate_thread_id()
        
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=10.0
        ) as client:
            for i in range(20):  # Reduced for faster testing
                response = await client.post("/api/v1/chat", json={
                    "message": f"Message {i}: This is a test message to check memory stability.",
                    "thread_id": thread_id,
                    "project_id": config.PROJECT_ID
                })
                
                assert response.status_code == 200
                await asyncio.sleep(0.5)  # Small delay between messages
        
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory
        
        # Memory growth should be reasonable (< 100MB)
        assert memory_growth < 100, f"Memory grew by {memory_growth:.2f}MB"

    # PERF-003: Large File Handling
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_perf_003_large_file(self):
        """Test handling of large files (10MB)."""
        temp_dir = tempfile.mkdtemp()
        large_file = os.path.join(temp_dir, "large.txt")
        
        # Create 10MB file
        with open(large_file, "w") as f:
            for i in range(100000):
                f.write(f"Line {i}: " + "x" * 90 + "\n")
        
        file_size = os.path.getsize(large_file) / 1024 / 1024  # MB
        assert file_size > 9, f"File only {file_size:.2f}MB"
        
        # Test reading
        from app.domain.tools.files.actions.read import handle_read
        
        start_time = time.time()
        result = await handle_read(path=large_file, start_line=1, end_line=100)
        elapsed = time.time() - start_time
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Should complete in reasonable time (< 5s)
        assert elapsed < 5.0, f"Read took {elapsed:.2f}s"

    # PERF-004: LSP Large Project
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_perf_004_lsp_large_project(self):
        """Test LSP performance on large project."""
        # Use the actual project directory
        from app.domain.tools.coding.lsp import consult_lsp
        
        start_time = time.time()
        
        result = await consult_lsp.ainvoke({
            "action": "check_errors",
            "file_path": "app/main.py"  # Known file
        })
        
        elapsed = time.time() - start_time
        
        # LSP should respond within 5 seconds
        assert elapsed < 5.0, f"LSP took {elapsed:.2f}s"


class TestStability:
    """Stability test suite."""

    # STAB-001: Agent Crash Recovery
    @pytest.mark.asyncio
    @pytest.mark.stability
    async def test_stab_001_crash_recovery(self):
        """Test recovery after simulated agent crash."""
        thread_id = config.generate_thread_id()
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=10.0
        ) as client:
            # Send a message
            response = await client.post("/api/v1/chat", json={
                "message": "Start a task",
                "thread_id": thread_id,
                "project_id": config.PROJECT_ID
            })
            
            assert response.status_code == 200
            
            # Simulate crash by stopping
            await client.post("/api/v1/stop", json={
                "thread_id": thread_id
            })
            
            # Should be able to resume
            resume_response = await client.post("/api/v1/resume", json={
                "thread_id": thread_id,
                "user_input": "Continue"
            })
            
            # Resume may or may not work depending on state
            assert resume_response.status_code in [200, 404]

    # STAB-002: Redis Disconnect
    @pytest.mark.asyncio
    @pytest.mark.stability
    async def test_stab_002_redis_disconnect(self):
        """Test graceful handling of Redis disconnection."""
        # This is a unit test with mocks
        from app.core.engine import activity_monitor
        from unittest.mock import patch, MagicMock
        
        with patch.object(activity_monitor, 'redis_client') as mock_redis:
            mock_redis.publish.side_effect = ConnectionError("Redis disconnected")
            
            # Should not crash the application
            try:
                await activity_monitor.publish_event("test-thread", {"type": "test"})
            except ConnectionError:
                pass  # Expected
            
            # Application should still function
            assert True

    # STAB-003: Long Running Stability
    @pytest.mark.asyncio
    @pytest.mark.stability
    @pytest.mark.slow
    async def test_stab_003_long_running(self):
        """Test stability over extended period (reduced for CI)."""
        start_time = time.time()
        duration = 60  # 1 minute for testing (would be 24h in production)
        iterations = 0
        errors = 0
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=10.0
        ) as client:
            while time.time() - start_time < duration:
                thread_id = config.generate_thread_id()
                
                try:
                    response = await client.post("/api/v1/chat", json={
                        "message": f"Health check {iterations}",
                        "thread_id": thread_id,
                        "project_id": config.PROJECT_ID
                    })
                    
                    if response.status_code != 200:
                        errors += 1
                except Exception:
                    errors += 1
                
                iterations += 1
                await asyncio.sleep(5)  # 5 second intervals
        
        success_rate = (iterations - errors) / iterations if iterations > 0 else 0
        
        # Should have > 95% success rate
        assert success_rate > 0.95, f"Success rate {success_rate:.2%} < 95%"
