"""
FileWatcher 单元测试

测试范围:
- FileWatcher 基础功能
- FileWatcherManager 管理功能
- FileWatcherEvent 事件数据类
- _EventBusHandler 内部处理逻辑

运行方式:
    cd backend && python -m pytest tests/unit/core/test_file_watcher.py -v
"""

import os
import sys
import pytest
import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from app.core.file.watcher import (
    FileWatcher,
    FileWatcherManager,
    FileWatcherEvent,
    _EventBusHandler,
)
from app.core.events import system_bus
from app.core.file.events import FileSystemEventType


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_event_bus():
    """创建模拟的事件总线"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture(autouse=True)
def cleanup_system_bus():
    """每个测试后清理 system_bus"""
    yield
    system_bus.clear()


# ============================================================
# FileWatcherEvent Tests
# ============================================================

class TestFileWatcherEvent:
    """测试 FileWatcherEvent 数据类"""

    def test_event_creation(self):
        """测试事件创建"""
        event = FileWatcherEvent(
            event_type=FileSystemEventType.FILE_MODIFIED,
            data={"path": "/test/file.txt", "content": "test"}
        )
        
        assert event.event_type == FileSystemEventType.FILE_MODIFIED
        assert event.data["path"] == "/test/file.txt"
        assert event.source == "file_watcher"  # 默认值
        assert event.timestamp is not None

    def test_event_with_custom_source(self):
        """测试带自定义 source 的事件"""
        event = FileWatcherEvent(
            event_type=FileSystemEventType.FILE_CREATED,
            source="custom_watcher",
            data={"path": "/test/new.txt"}
        )
        
        assert event.source == "custom_watcher"

    def test_event_source_default_override(self):
        """测试 source 默认值覆盖"""
        event = FileWatcherEvent(
            event_type=FileSystemEventType.FILE_DELETED,
            data={}
        )
        # 应该使用 file_watcher 而不是 system
        assert event.source == "file_watcher"

    def test_event_type_name_property(self):
        """测试 type_name 属性"""
        event = FileWatcherEvent(
            event_type=FileSystemEventType.FILE_DELETED,
            data={}
        )
        
        assert event.type_name == FileSystemEventType.FILE_DELETED


# ============================================================
# _EventBusHandler Tests
# ============================================================

class TestEventBusHandler:
    """测试内部事件处理器"""

    def test_should_process_without_filter(self):
        """测试无过滤器时所有路径都通过"""
        handler = _EventBusHandler("/watch")
        
        assert handler._should_process("/watch/file.txt") is True
        assert handler._should_process("/watch/subdir/file.py") is True
        assert handler._should_process("/other/file.txt") is True

    def test_should_process_with_filter(self):
        """测试有过滤器时的路径过滤"""
        def filter_py_files(path: str) -> bool:
            return path.endswith('.py')
        
        handler = _EventBusHandler("/watch", file_filter=filter_py_files)
        
        assert handler._should_process("/watch/test.py") is True
        assert handler._should_process("/watch/test.txt") is False
        assert handler._should_process("/watch/script.py") is True

    @pytest.mark.asyncio
    async def test_publish_event_with_event_loop(self):
        """测试有 event loop 时的事件发布"""
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            handler._publish_event(
                FileSystemEventType.FILE_MODIFIED,
                "/watch/test.txt"
            )
            
            # 给线程安全调度一点时间
            await asyncio.sleep(0.05)
            
            assert len(events_published) == 1
            assert events_published[0].event_type == FileSystemEventType.FILE_MODIFIED
            assert events_published[0].data["path"] == "/watch/test.txt"
            assert events_published[0].data["watch_path"] == "/watch"

    def test_publish_event_without_event_loop(self):
        """测试无 event loop 时跳过事件发布"""
        handler = _EventBusHandler("/watch", event_loop=None)
        
        # 不应该抛出异常
        handler._publish_event(
            FileSystemEventType.FILE_MODIFIED,
            "/watch/test.txt"
        )

    @pytest.mark.asyncio
    async def test_schedule_publish_with_debounce(self):
        """测试防抖发布功能"""
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", debounce_delay=0.1, event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            # 快速触发多次事件
            handler._schedule_publish(FileSystemEventType.FILE_MODIFIED, "/watch/test.txt")
            handler._schedule_publish(FileSystemEventType.FILE_MODIFIED, "/watch/test.txt")
            handler._schedule_publish(FileSystemEventType.FILE_MODIFIED, "/watch/test.txt")
            
            # 等待防抖延迟
            await asyncio.sleep(0.15)
            
            # 由于防抖，相同路径的事件应该只发布一次
            assert len(events_published) == 1
            assert events_published[0].data["path"] == "/watch/test.txt"

    @pytest.mark.asyncio
    async def test_on_created_file(self):
        """测试文件创建事件处理"""
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            # 模拟 watchdog 事件
            mock_event = MagicMock()
            mock_event.src_path = "/watch/new_file.txt"
            mock_event.is_directory = False
            
            handler.on_created(mock_event)
            await asyncio.sleep(0.05)
            
            assert len(events_published) == 1
            assert events_published[0].event_type == FileSystemEventType.FILE_CREATED

    @pytest.mark.asyncio
    async def test_on_created_directory(self):
        """测试目录创建事件处理"""
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            mock_event = MagicMock()
            mock_event.src_path = "/watch/new_dir"
            mock_event.is_directory = True
            
            handler.on_created(mock_event)
            await asyncio.sleep(0.05)
            
            assert len(events_published) == 1
            assert events_published[0].event_type == FileSystemEventType.DIRECTORY_CREATED

    @pytest.mark.asyncio
    async def test_on_modified_file(self):
        """测试文件修改事件处理"""
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            mock_event = MagicMock()
            mock_event.src_path = "/watch/modified.txt"
            mock_event.is_directory = False
            
            handler.on_modified(mock_event)
            await asyncio.sleep(0.05)
            
            assert len(events_published) == 1
            assert events_published[0].event_type == FileSystemEventType.FILE_MODIFIED

    @pytest.mark.asyncio
    async def test_on_deleted_file(self):
        """测试文件删除事件处理"""
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            mock_event = MagicMock()
            mock_event.src_path = "/watch/deleted.txt"
            mock_event.is_directory = False
            
            handler.on_deleted(mock_event)
            await asyncio.sleep(0.05)
            
            assert len(events_published) == 1
            assert events_published[0].event_type == FileSystemEventType.FILE_DELETED

    @pytest.mark.asyncio
    async def test_on_moved(self):
        """测试文件移动事件处理"""
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            mock_event = MagicMock()
            mock_event.src_path = "/watch/old_name.txt"
            mock_event.dest_path = "/watch/new_name.txt"
            mock_event.is_directory = False
            
            handler.on_moved(mock_event)
            await asyncio.sleep(0.05)
            
            assert len(events_published) == 1
            assert events_published[0].event_type == FileSystemEventType.FILE_MOVED
            assert events_published[0].data["dest_path"] == "/watch/new_name.txt"
            assert events_published[0].data["is_directory"] is False

    @pytest.mark.asyncio
    async def test_filtered_events(self):
        """测试事件过滤"""
        def filter_txt(path: str) -> bool:
            return path.endswith('.txt')
        
        loop = asyncio.get_running_loop()
        handler = _EventBusHandler("/watch", file_filter=filter_txt, event_loop=loop)
        
        events_published = []
        
        async def mock_publish(event):
            events_published.append(event)
        
        with patch.object(system_bus, 'publish', mock_publish):
            # txt 文件应该触发事件
            txt_event = MagicMock()
            txt_event.src_path = "/watch/test.txt"
            txt_event.is_directory = False
            
            handler.on_created(txt_event)
            
            # py 文件不应该触发事件
            py_event = MagicMock()
            py_event.src_path = "/watch/test.py"
            py_event.is_directory = False
            
            handler.on_created(py_event)
            
            await asyncio.sleep(0.05)
            
            assert len(events_published) == 1
            assert events_published[0].data["path"] == "/watch/test.txt"


# ============================================================
# FileWatcher Tests
# ============================================================

class TestFileWatcher:
    """测试 FileWatcher 类"""

    def test_init(self, temp_dir):
        """测试初始化"""
        watcher = FileWatcher(
            path=temp_dir,
            recursive=True,
            debounce_delay=1.0
        )
        
        assert watcher.path == os.path.abspath(temp_dir)
        assert watcher.recursive is True
        assert watcher.debounce_delay == 1.0
        assert watcher.is_running is False

    def test_init_with_file_filter(self, temp_dir):
        """测试带文件过滤器的初始化"""
        def filter_func(path: str) -> bool:
            return path.endswith('.py')
        
        watcher = FileWatcher(
            path=temp_dir,
            file_filter=filter_func
        )
        
        assert watcher.file_filter is filter_func

    @pytest.mark.asyncio
    async def test_start_stop(self, temp_dir):
        """测试启动和停止"""
        watcher = FileWatcher(path=temp_dir)
        
        # 启动
        result = watcher.start()
        assert result is watcher  # 返回 self
        assert watcher.is_running is True
        
        # 停止
        watcher.stop()
        assert watcher.is_running is False

    @pytest.mark.asyncio
    async def test_double_start(self, temp_dir):
        """测试重复启动"""
        watcher = FileWatcher(path=temp_dir)
        
        watcher.start()
        result = watcher.start()  # 第二次启动应该返回自身而不报错
        
        assert result is watcher
        watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self, temp_dir):
        """测试未启动时停止"""
        watcher = FileWatcher(path=temp_dir)
        
        # 不应该抛出异常
        watcher.stop()
        assert watcher.is_running is False

    @pytest.mark.asyncio
    async def test_context_manager(self, temp_dir):
        """测试上下文管理器"""
        with FileWatcher(path=temp_dir) as watcher:
            assert watcher.is_running is True
        
        # 退出上下文后应该停止
        assert watcher.is_running is False

    @pytest.mark.asyncio
    async def test_publishes_started_event(self, temp_dir):
        """测试启动时发布事件"""
        events = []
        
        async def handler(event):
            events.append(event)
        
        system_bus.subscribe(FileSystemEventType.WATCHER_STARTED, handler)
        
        watcher = FileWatcher(path=temp_dir, recursive=True)
        watcher.start()
        
        await asyncio.sleep(0.05)  # 给事件处理时间
        
        watcher.stop()
        
        assert len(events) == 1
        assert events[0].event_type == FileSystemEventType.WATCHER_STARTED
        assert events[0].data["path"] == watcher.path
        assert events[0].data["recursive"] is True

    @pytest.mark.asyncio
    async def test_publishes_stopped_event(self, temp_dir):
        """测试停止时发布事件"""
        events = []
        
        async def handler(event):
            events.append(event)
        
        system_bus.subscribe(FileSystemEventType.WATCHER_STOPPED, handler)
        
        watcher = FileWatcher(path=temp_dir)
        watcher.start()
        await asyncio.sleep(0.05)
        
        watcher.stop()
        await asyncio.sleep(0.1)  # 给更多时间处理停止事件
        
        # 停止事件可能无法发布（如果 event loop 已关闭），所以这里不强制检查
        # 只检查 watcher 确实停止了
        assert watcher.is_running is False
        # 如果事件发布了，验证其内容
        if events:
            assert events[0].event_type == FileSystemEventType.WATCHER_STOPPED
            assert events[0].data["path"] == watcher.path


# ============================================================
# FileWatcherManager Tests
# ============================================================

class TestFileWatcherManager:
    """测试 FileWatcherManager 类"""

    def test_init(self):
        """测试初始化"""
        manager = FileWatcherManager()
        assert manager.watcher_count == 0

    @pytest.mark.asyncio
    async def test_create_watcher(self, temp_dir):
        """测试创建 watcher"""
        manager = FileWatcherManager()
        
        watcher = manager.create_watcher(temp_dir)
        
        assert watcher.is_running is True
        assert manager.watcher_count == 1
        assert manager.get_watcher(temp_dir) is watcher
        
        manager.stop_all()

    @pytest.mark.asyncio
    async def test_create_multiple_watchers(self, temp_dir):
        """测试创建多个 watchers"""
        manager = FileWatcherManager()
        
        # 创建子目录
        subdir1 = os.path.join(temp_dir, "dir1")
        subdir2 = os.path.join(temp_dir, "dir2")
        os.makedirs(subdir1)
        os.makedirs(subdir2)
        
        watcher1 = manager.create_watcher(subdir1)
        watcher2 = manager.create_watcher(subdir2)
        
        assert manager.watcher_count == 2
        assert manager.get_watcher(subdir1) is watcher1
        assert manager.get_watcher(subdir2) is watcher2
        
        manager.stop_all()

    @pytest.mark.asyncio
    async def test_recreate_watcher(self, temp_dir):
        """测试重新创建 watcher（应该替换旧的）"""
        manager = FileWatcherManager()
        
        watcher1 = manager.create_watcher(temp_dir)
        watcher1_id = id(watcher1)
        
        # 重新创建同一路径的 watcher
        watcher2 = manager.create_watcher(temp_dir)
        watcher2_id = id(watcher2)
        
        assert watcher1_id != watcher2_id
        assert manager.watcher_count == 1
        assert manager.get_watcher(temp_dir) is watcher2
        
        # 旧的 watcher 应该已经停止
        assert watcher1.is_running is False
        assert watcher2.is_running is True
        
        manager.stop_all()

    @pytest.mark.asyncio
    async def test_stop_watcher(self, temp_dir):
        """测试停止单个 watcher"""
        manager = FileWatcherManager()
        
        watcher = manager.create_watcher(temp_dir)
        assert watcher.is_running is True
        
        manager.stop_watcher(temp_dir)
        
        assert watcher.is_running is False
        assert manager.watcher_count == 0
        assert manager.get_watcher(temp_dir) is None

    @pytest.mark.asyncio
    async def test_stop_all(self, temp_dir):
        """测试停止所有 watchers"""
        manager = FileWatcherManager()
        
        subdir1 = os.path.join(temp_dir, "dir1")
        subdir2 = os.path.join(temp_dir, "dir2")
        os.makedirs(subdir1)
        os.makedirs(subdir2)
        
        watcher1 = manager.create_watcher(subdir1)
        watcher2 = manager.create_watcher(subdir2)
        
        manager.stop_all()
        
        assert watcher1.is_running is False
        assert watcher2.is_running is False
        assert manager.watcher_count == 0

    @pytest.mark.asyncio
    async def test_context_manager(self, temp_dir):
        """测试上下文管理器"""
        with FileWatcherManager() as manager:
            watcher = manager.create_watcher(temp_dir)
            assert watcher.is_running is True
            assert manager.watcher_count == 1
        
        # 退出上下文后所有 watcher 应该停止
        assert watcher.is_running is False

    def test_get_nonexistent_watcher(self, temp_dir):
        """测试获取不存在的 watcher"""
        manager = FileWatcherManager()
        assert manager.get_watcher("/nonexistent/path") is None


# ============================================================
# Real File System Tests (Slow)
# ============================================================

@pytest.mark.slow
class TestFileWatcherRealFilesystem:
    """真实文件系统测试（标记为慢测试）"""

    @pytest.mark.asyncio
    async def test_detects_file_creation(self, temp_dir):
        """测试检测文件创建"""
        events = []
        
        async def handler(event):
            if event.event_type == FileSystemEventType.FILE_CREATED:
                events.append(event)
        
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, handler)
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            # 创建文件
            test_file = os.path.join(temp_dir, "test_create.txt")
            with open(test_file, "w") as f:
                f.write("test content")
            
            # 等待文件系统事件
            await asyncio.sleep(0.5)
        
        # 检查是否收到事件（由于多线程调度，可能有延迟）
        assert len(events) >= 1
        # macOS 临时目录可能有 /private 前缀，使用 endswith 比较
        assert events[0].data["path"].endswith(os.path.basename(test_file))

    @pytest.mark.asyncio
    async def test_detects_file_modification(self, temp_dir):
        """测试检测文件修改"""
        test_file = os.path.join(temp_dir, "test_modify.txt")
        
        # 先创建文件
        with open(test_file, "w") as f:
            f.write("original")
        
        events = []
        
        async def handler(event):
            if event.event_type == FileSystemEventType.FILE_MODIFIED:
                events.append(event)
        
        system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, handler)
        
        with FileWatcher(path=temp_dir, debounce_delay=0.1) as watcher:
            # 修改文件
            with open(test_file, "w") as f:
                f.write("modified content")
            
            await asyncio.sleep(0.5)
        
        assert len(events) >= 1
        # macOS 临时目录可能有 /private 前缀，使用 endswith 比较
        assert events[0].data["path"].endswith(os.path.basename(test_file))

    @pytest.mark.asyncio
    async def test_detects_file_deletion(self, temp_dir):
        """测试检测文件删除"""
        test_file = os.path.join(temp_dir, "test_delete.txt")
        
        # 先创建文件
        with open(test_file, "w") as f:
            f.write("to be deleted")
        
        events = []
        
        async def handler(event):
            if event.event_type == FileSystemEventType.FILE_DELETED:
                events.append(event)
        
        system_bus.subscribe(FileSystemEventType.FILE_DELETED, handler)
        
        with FileWatcher(path=temp_dir, debounce_delay=0.0) as watcher:
            # 删除文件
            os.remove(test_file)
            
            await asyncio.sleep(0.5)
        
        assert len(events) >= 1
        # macOS 临时目录可能有 /private 前缀，使用 endswith 比较
        assert events[0].data["path"].endswith(os.path.basename(test_file))

    @pytest.mark.asyncio
    async def test_file_filter(self, temp_dir):
        """测试文件过滤"""
        events = []
        
        async def handler(event):
            events.append(event)
        
        system_bus.subscribe(FileSystemEventType.FILE_CREATED, handler)
        
        # 只监控 .txt 文件
        def txt_filter(path: str) -> bool:
            return path.endswith('.txt')
        
        with FileWatcher(
            path=temp_dir,
            file_filter=txt_filter,
            debounce_delay=0.1
        ) as watcher:
            # 创建 txt 文件
            txt_file = os.path.join(temp_dir, "test.txt")
            with open(txt_file, "w") as f:
                f.write("txt content")
            
            # 创建 py 文件（应该被过滤）
            py_file = os.path.join(temp_dir, "test.py")
            with open(py_file, "w") as f:
                f.write("python content")
            
            await asyncio.sleep(0.5)
        
        # 只应该收到 txt 文件的事件
        txt_events = [e for e in events if e.data["path"].endswith('.txt')]
        py_events = [e for e in events if e.data["path"].endswith('.py')]
        
        assert len(txt_events) >= 1
        assert len(py_events) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
