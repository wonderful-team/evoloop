"""
FileWatcher 与 Event System 集成测试

测试范围:
- FileWatcher 与 system_bus 的集成
- 事件订阅和发布的端到端流程
- 多订阅者场景
- 事件数据完整性验证
- 错误处理和恢复

运行方式:
    cd backend && python -m pytest tests/integration/test_file_watcher_events.py -v
"""

import os
import sys
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.core.file.watcher import (
    FileWatcher,
    FileWatcherManager,
)
from app.core.file.event.schemas import FileWatcherEvent
from app.core.events import system_bus, AsyncEventBus, BaseEvent
from app.core.file.event.types import FileSystemEventType


# Helper function to compare paths (handles macOS /private prefix)
def paths_equal(path1: str, path2: str) -> bool:
    """比较两个路径是否相同（处理 macOS /private 前缀）"""
    real_path1 = os.path.realpath(path1)
    real_path2 = os.path.realpath(path2)
    return real_path1 == real_path2


def path_in_paths(path: str, paths: list) -> bool:
    """检查路径是否在路径列表中（处理 macOS /private 前缀）"""
    real_path = os.path.realpath(path)
    real_paths = [os.path.realpath(p) for p in paths]
    return real_path in real_paths


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(autouse=True)
def cleanup_system_bus():
    """每个测试后清理 system_bus"""
    yield
    system_bus.clear()


@pytest.fixture
def event_collector():
    """事件收集器 fixture"""
    class EventCollector:
        def __init__(self):
            self.events = []
        
        async def handler(self, event):
            self.events.append(event)
        
        def get_by_type(self, event_type):
            return [e for e in self.events if e.event_type == event_type]
        
        def clear(self):
            self.events.clear()
    
    return EventCollector()


# ============================================================
# Basic Integration Tests
# ============================================================

class TestFileWatcherEventBusIntegration:
    """测试 FileWatcher 与 EventBus 的基础集成"""

    @pytest.mark.asyncio
    async def test_watcher_publishes_to_system_bus(self, temp_dir, event_collector):
        """测试 watcher 正确发布事件到 system_bus"""
        system_bus.subscribe(
            FileSystemEventType.WATCHER_STARTED,
            event_collector.handler
        )
        
        watcher = FileWatcher(path=temp_dir)
        watcher.start()
        
        await asyncio.sleep(0.05)
        
        watcher.stop()
        
        started_events = event_collector.get_by_type(FileSystemEventType.WATCHER_STARTED)
        assert len(started_events) == 1
        assert started_events[0].data["path"] == watcher.path

    @pytest.mark.asyncio
    async def test_file_created_event_flow(self, temp_dir, event_collector):
        """测试文件创建事件的完整流程"""
        system_bus.subscribe(
            FileSystemEventType.FILE_CREATED,
            event_collector.handler
        )
        
        test_file = os.path.join(temp_dir, "integration_test.txt")
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            # 创建文件
            with open(test_file, "w") as f:
                f.write("integration test")
            
            await asyncio.sleep(0.3)
        
        created_events = event_collector.get_by_type(FileSystemEventType.FILE_CREATED)
        assert len(created_events) >= 1
        assert any(paths_equal(e.data["path"], test_file) for e in created_events)

    @pytest.mark.asyncio
    async def test_file_modified_event_flow(self, temp_dir, event_collector):
        """测试文件修改事件的完整流程"""
        test_file = os.path.join(temp_dir, "modify_test.txt")
        
        # 先创建文件
        with open(test_file, "w") as f:
            f.write("original")
        
        system_bus.subscribe(
            FileSystemEventType.FILE_MODIFIED,
            event_collector.handler
        )
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            # 修改文件
            with open(test_file, "w") as f:
                f.write("modified content")
            
            await asyncio.sleep(0.3)
        
        modified_events = event_collector.get_by_type(FileSystemEventType.FILE_MODIFIED)
        assert len(modified_events) >= 1
        assert any(paths_equal(e.data["path"], test_file) for e in modified_events)

    @pytest.mark.asyncio
    async def test_file_deleted_event_flow(self, temp_dir, event_collector):
        """测试文件删除事件的完整流程"""
        test_file = os.path.join(temp_dir, "delete_test.txt")
        
        # 先创建文件
        with open(test_file, "w") as f:
            f.write("to be deleted")
        
        system_bus.subscribe(
            FileSystemEventType.FILE_DELETED,
            event_collector.handler
        )
        
        with FileWatcher(path=temp_dir, debounce_delay=0.0) as watcher:
            # 删除文件
            os.remove(test_file)
            
            await asyncio.sleep(0.3)
        
        deleted_events = event_collector.get_by_type(FileSystemEventType.FILE_DELETED)
        assert len(deleted_events) >= 1
        assert any(paths_equal(e.data["path"], test_file) for e in deleted_events)


# ============================================================
# Multi-Subscriber Tests
# ============================================================

class TestMultiSubscriberScenarios:
    """测试多订阅者场景"""

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self, temp_dir):
        """测试同一事件的多个处理器"""
        handler1_events = []
        handler2_events = []
        
        async def handler1(event):
            handler1_events.append(event)
        
        async def handler2(event):
            handler2_events.append(event)
        
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, handler1)
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, handler2)
        
        with FileWatcher(path=temp_dir) as watcher:
            await asyncio.sleep(0.05)
        
        assert len(handler1_events) == 1
        assert len(handler2_events) == 1
        assert handler1_events[0].event_type == FileSystemEventType.WATCHER_STARTED
        assert handler2_events[0].event_type == FileSystemEventType.WATCHER_STARTED

    @pytest.mark.asyncio
    async def test_different_handlers_different_events(self, temp_dir):
        """测试不同事件的不同处理器"""
        started_events = []
        created_events = []
        
        async def on_started(event):
            if event.event_type == FileSystemEventType.WATCHER_STARTED:
                started_events.append(event)
        
        async def on_created(event):
            if event.event_type == FileSystemEventType.FILE_CREATED:
                created_events.append(event)
        
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, on_started)
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, on_created)
        
        test_file = os.path.join(temp_dir, "multi_handler.txt")
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            await asyncio.sleep(0.05)  # 等待 started 事件
            
            with open(test_file, "w") as f:
                f.write("test")
            
            await asyncio.sleep(0.3)
        
        assert len(started_events) >= 1
        assert len(created_events) >= 1

    @pytest.mark.asyncio
    async def test_global_handler_receives_all_events(self, temp_dir):
        """测试全局处理器接收所有事件"""
        all_events = []
        
        async def global_handler(event):
            all_events.append(event)
        
        system_bus.subscribe_all(global_handler)
        
        test_file = os.path.join(temp_dir, "global_test.txt")
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            with open(test_file, "w") as f:
                f.write("test")
            
            await asyncio.sleep(0.3)
        
        # 全局处理器应该收到多种类型的事件
        event_types = set(e.event_type for e in all_events)
        assert FileSystemEventType.WATCHER_STARTED in event_types
        assert FileSystemEventType.FILE_CREATED in event_types
        # WATCHER_STOPPED 可能收不到（停止时 event loop 可能已关闭），所以不强制检查


# ============================================================
# Event Data Integrity Tests
# ============================================================

class TestEventDataIntegrity:
    """测试事件数据完整性"""

    @pytest.mark.asyncio
    async def test_event_data_contains_required_fields(self, temp_dir, event_collector):
        """测试事件数据包含必需字段"""
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, event_collector.handler)
        
        test_file = os.path.join(temp_dir, "data_test.txt")
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            with open(test_file, "w") as f:
                f.write("test")
            
            await asyncio.sleep(0.3)
        
        events = event_collector.get_by_type(FileSystemEventType.FILE_CREATED)
        assert len(events) >= 1
        
        event = events[0]
        # 验证必需字段
        assert "path" in event.data
        assert "watch_path" in event.data
        assert paths_equal(event.data["path"], test_file)
        assert paths_equal(event.data["watch_path"], watcher.path)

    @pytest.mark.asyncio
    async def test_file_moved_event_data(self, temp_dir, event_collector):
        """测试文件移动事件的数据完整性"""
        system_bus.subscribe(FileSystemEventType.FILE_MOVED, event_collector.handler)
        
        src_file = os.path.join(temp_dir, "source.txt")
        dest_file = os.path.join(temp_dir, "destination.txt")
        
        # 创建源文件
        with open(src_file, "w") as f:
            f.write("move me")
        
        with FileWatcher(path=temp_dir, debounce_delay=0.0) as watcher:
            # 移动文件
            os.rename(src_file, dest_file)
            
            await asyncio.sleep(0.3)
        
        moved_events = event_collector.get_by_type(FileSystemEventType.FILE_MOVED)
        assert len(moved_events) >= 1
        
        event = moved_events[0]
        assert paths_equal(event.data["path"], src_file)
        assert paths_equal(event.data["dest_path"], dest_file)
        assert "is_directory" in event.data

    @pytest.mark.asyncio
    async def test_event_timestamp(self, temp_dir, event_collector):
        """测试事件时间戳"""
        from datetime import datetime
        
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, event_collector.handler)
        
        before_start = datetime.now()
        
        with FileWatcher(path=temp_dir) as watcher:
            await asyncio.sleep(0.05)
        
        after_stop = datetime.now()
        
        events = event_collector.get_by_type(FileSystemEventType.WATCHER_STARTED)
        assert len(events) == 1
        
        event_timestamp = events[0].timestamp
        assert before_start <= event_timestamp <= after_stop

    @pytest.mark.asyncio
    async def test_event_source(self, temp_dir, event_collector):
        """测试事件来源"""
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, event_collector.handler)
        
        with FileWatcher(path=temp_dir) as watcher:
            await asyncio.sleep(0.05)
        
        events = event_collector.get_by_type(FileSystemEventType.WATCHER_STARTED)
        assert len(events) == 1
        assert events[0].source == "file_watcher"


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling:
    """测试错误处理"""

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self, temp_dir):
        """测试处理器错误隔离 - 一个处理器失败不影响其他"""
        good_handler_events = []
        
        async def failing_handler(event):
            raise Exception("Handler failed!")
        
        async def good_handler(event):
            good_handler_events.append(event)
        
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, failing_handler)
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, good_handler)
        
        # 不应该抛出异常
        with FileWatcher(path=temp_dir) as watcher:
            await asyncio.sleep(0.05)
        
        # 好的处理器应该仍然收到事件
        assert len(good_handler_events) == 1

    @pytest.mark.asyncio
    async def test_watcher_survives_event_publish_error(self, temp_dir):
        """测试 watcher 在事件发布错误后继续运行"""
        async def failing_handler(event):
            raise Exception("Publish failed!")
        
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, failing_handler)
        
        test_file = os.path.join(temp_dir, "error_test.txt")
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            # 这个操作不应该导致 watcher 崩溃
            with open(test_file, "w") as f:
                f.write("test")
            
            await asyncio.sleep(0.3)
            
            # Watcher 应该仍在运行
            assert watcher.is_running


# ============================================================
# FileWatcherManager Integration Tests
# ============================================================

class TestFileWatcherManagerIntegration:
    """测试 FileWatcherManager 的集成场景"""

    @pytest.mark.asyncio
    async def test_manager_with_multiple_paths(self, temp_dir, event_collector):
        """测试管理器监控多个路径"""
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, event_collector.handler)
        
        # 创建子目录
        dir1 = os.path.join(temp_dir, "project1")
        dir2 = os.path.join(temp_dir, "project2")
        os.makedirs(dir1)
        os.makedirs(dir2)
        
        with FileWatcherManager() as manager:
            manager.create_watcher(dir1)
            manager.create_watcher(dir2)
            
            # 在两个目录中创建文件
            file1 = os.path.join(dir1, "file1.txt")
            file2 = os.path.join(dir2, "file2.txt")
            
            with open(file1, "w") as f:
                f.write("content1")
            with open(file2, "w") as f:
                f.write("content2")
            
            await asyncio.sleep(0.3)
        
        created_events = event_collector.get_by_type(FileSystemEventType.FILE_CREATED)
        paths = [e.data["path"] for e in created_events]
        
        assert path_in_paths(file1, paths)
        assert path_in_paths(file2, paths)

    @pytest.mark.asyncio
    async def test_manager_isolated_events(self, temp_dir, event_collector):
        """测试管理器隔离不同路径的事件"""
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, event_collector.handler)
        
        watched_dir = os.path.join(temp_dir, "watched")
        unwatched_dir = os.path.join(temp_dir, "unwatched")
        os.makedirs(watched_dir)
        os.makedirs(unwatched_dir)
        
        with FileWatcherManager() as manager:
            manager.create_watcher(watched_dir)
            
            # 在监控目录创建文件
            watched_file = os.path.join(watched_dir, "watched.txt")
            with open(watched_file, "w") as f:
                f.write("watched")
            
            # 在未监控目录创建文件
            unwatched_file = os.path.join(unwatched_dir, "unwatched.txt")
            with open(unwatched_file, "w") as f:
                f.write("unwatched")
            
            await asyncio.sleep(0.3)
        
        created_events = event_collector.get_by_type(FileSystemEventType.FILE_CREATED)
        paths = [e.data["path"] for e in created_events]
        
        assert path_in_paths(watched_file, paths)
        assert not path_in_paths(unwatched_file, paths)


# ============================================================
# Performance Tests
# ============================================================

@pytest.mark.slow
class TestPerformance:
    """性能测试"""

    @pytest.mark.asyncio
    async def test_rapid_file_changes(self, temp_dir, event_collector):
        """测试快速文件变更处理"""
        system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, event_collector.handler)
        
        test_file = os.path.join(temp_dir, "rapid.txt")
        
        # 先创建文件
        with open(test_file, "w") as f:
            f.write("initial")
        
        with FileWatcher(path=temp_dir, debounce_delay=0.05) as watcher:
            # 快速多次修改
            for i in range(10):
                with open(test_file, "w") as f:
                    f.write(f"content {i}")
                await asyncio.sleep(0.01)
            
            # 等待防抖
            await asyncio.sleep(0.2)
        
        modified_events = event_collector.get_by_type(FileSystemEventType.FILE_MODIFIED)
        # 由于防抖，应该只有少量事件
        assert len(modified_events) <= 3

    @pytest.mark.asyncio
    async def test_many_files_creation(self, temp_dir, event_collector):
        """测试大量文件创建"""
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, event_collector.handler)
        
        with FileWatcher(path=temp_dir, debounce_delay=0.0) as watcher:
            # 创建多个文件
            for i in range(20):
                file_path = os.path.join(temp_dir, f"file_{i}.txt")
                with open(file_path, "w") as f:
                    f.write(f"content {i}")
            
            await asyncio.sleep(0.5)
        
        created_events = event_collector.get_by_type(FileSystemEventType.FILE_CREATED)
        # 应该收到所有文件创建事件
        assert len(created_events) >= 20


# ============================================================
# Edge Case Tests
# ============================================================

class TestEdgeCases:
    """边缘情况测试"""

    @pytest.mark.asyncio
    async def test_empty_directory_watcher(self, temp_dir, event_collector):
        """测试空目录监控"""
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, event_collector.handler)
        
        with FileWatcher(path=temp_dir) as watcher:
            await asyncio.sleep(0.05)
        
        events = event_collector.get_by_type(FileSystemEventType.WATCHER_STARTED)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_nested_directory_operations(self, temp_dir, event_collector):
        """测试嵌套目录操作"""
        system_bus.subscribe(FileSystemEventType.DIRECTORY_CREATED, event_collector.handler)
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, event_collector.handler)
        
        with FileWatcher(path=temp_dir, recursive=True, debounce_delay=0.1) as watcher:
            # 创建嵌套目录
            nested_dir = os.path.join(temp_dir, "level1", "level2")
            os.makedirs(nested_dir)
            
            # 在嵌套目录创建文件
            nested_file = os.path.join(nested_dir, "deep.txt")
            with open(nested_file, "w") as f:
                f.write("deep content")
            
            await asyncio.sleep(0.3)
        
        dir_events = event_collector.get_by_type(FileSystemEventType.DIRECTORY_CREATED)
        file_events = event_collector.get_by_type(FileSystemEventType.FILE_CREATED)
        
        # 应该收到目录创建事件
        assert len(dir_events) >= 2  # level1 和 level2
        
        # 应该收到文件创建事件
        assert any(paths_equal(e.data["path"], nested_file) for e in file_events)

    @pytest.mark.asyncio
    async def test_special_characters_in_filename(self, temp_dir, event_collector):
        """测试特殊字符文件名"""
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, event_collector.handler)
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            # 使用特殊字符创建文件
            special_names = [
                "file with spaces.txt",
                "file-with-dashes.txt",
                "file_with_underscores.txt",
                "file.multiple.dots.txt",
                "unicode_文件.txt",
            ]
            
            for name in special_names:
                file_path = os.path.join(temp_dir, name)
                with open(file_path, "w") as f:
                    f.write("test")
            
            await asyncio.sleep(0.3)
        
        created_events = event_collector.get_by_type(FileSystemEventType.FILE_CREATED)
        created_paths = [e.data["path"] for e in created_events]
        
        for name in special_names:
            expected_path = os.path.join(temp_dir, name)
            assert path_in_paths(expected_path, created_paths)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
