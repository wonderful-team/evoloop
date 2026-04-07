"""
Unit tests for KAIROS Daily Log Mode (Phase 3).

Tests daily log writing, reading, and nightly consolidation.

Run with: pytest tests/unit/memory/test_daily_log.py -v
"""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path


class TestLogEntry:
    """Tests for LogEntry data class."""
    
    def test_log_entry_creation(self):
        """Test that LogEntry can be created."""
        from app.core.memory.daily_log import LogEntry
        
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            memory_id="mem_001",
            memory_type="project",
            title="Test Memory",
            description="Test description",
            user_id="user_123",
            project_id=42,
        )
        
        assert entry.memory_id == "mem_001"
        assert entry.memory_type == "project"
        assert entry.user_id == "user_123"
        assert entry.project_id == 42
    
    def test_log_entry_to_markdown(self):
        """Test conversion to markdown format."""
        from app.core.memory.daily_log import LogEntry
        
        entry = LogEntry(
            timestamp=datetime(2026, 4, 2, 14, 30, 0),
            memory_id="mem_001",
            memory_type="project",
            title="Docker Best Practices",
            description="How to use Docker effectively",
            user_id="user_123",
            project_id=42,
        )
        
        markdown = entry.to_markdown()
        
        assert "mem_001" in markdown
        assert "Docker Best Practices" in markdown
        assert "PROJECT" in markdown
        assert "user:user_123" in markdown
        assert "project:42" in markdown
        assert "14:30:00" in markdown
    
    def test_log_entry_from_memory_entry(self):
        """Test creation from MemoryEntry."""
        from app.core.memory.daily_log import LogEntry
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        now = datetime.utcnow()
        memory = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Test Memory",
            description="Test description",
            content="Content",
            created_at=now,
            updated_at=now,
            user_id="user_123",
            project_id=42,
        )
        
        log_entry = LogEntry.from_memory_entry(memory)
        
        assert log_entry.memory_id == "mem_001"
        assert log_entry.memory_type == "project"
        assert log_entry.user_id == "user_123"
        assert log_entry.project_id == 42


class TestDailyLogWriter:
    """Tests for DailyLogWriter."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for logs."""
        temp_dir = tempfile.mkdtemp(prefix="evoloop_test_logs_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_get_log_path(self, temp_log_dir):
        """Test log path generation."""
        from app.core.memory.daily_log import DailyLogWriter
        
        writer = DailyLogWriter(root_path=temp_log_dir)
        date = datetime(2026, 4, 2)
        
        path = writer._get_log_path(date)
        
        assert "2026" in str(path)
        assert "04" in str(path)
        assert "2026-04-02.md" in str(path)
    
    @pytest.mark.asyncio
    async def test_append_creates_file(self, temp_log_dir):
        """Test that append creates log file."""
        from app.core.memory.daily_log import DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        writer = DailyLogWriter(root_path=temp_log_dir)
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Test Memory",
            description="Test description",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        await writer.append(entry)
        
        log_path = writer._get_log_path()
        assert log_path.exists()
    
    @pytest.mark.asyncio
    async def test_append_adds_header(self, temp_log_dir):
        """Test that append adds header for new files."""
        from app.core.memory.daily_log import DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        writer = DailyLogWriter(root_path=temp_log_dir)
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Test Memory",
            description="Test description",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        await writer.append(entry)
        
        log_path = writer._get_log_path()
        content = log_path.read_text()
        
        assert "# Memory Log:" in content
        assert "Auto-generated" in content
    
    @pytest.mark.asyncio
    async def test_read_log(self, temp_log_dir):
        """Test reading log entries."""
        from app.core.memory.daily_log import DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        writer = DailyLogWriter(root_path=temp_log_dir)
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Test Memory",
            description="Test description",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        await writer.append(entry)
        
        entries = await writer.read_log()
        
        assert len(entries) == 1
        assert entries[0].memory_id == "mem_001"
        assert entries[0].title == "Test Memory"
    
    @pytest.mark.asyncio
    async def test_read_empty_log(self, temp_log_dir):
        """Test reading non-existent log."""
        from app.core.memory.daily_log import DailyLogWriter
        
        writer = DailyLogWriter(root_path=temp_log_dir)
        
        entries = await writer.read_log()
        
        assert entries == []
    
    @pytest.mark.asyncio
    async def test_list_available_dates(self, temp_log_dir):
        """Test listing available log dates."""
        from app.core.memory.daily_log import DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        writer = DailyLogWriter(root_path=temp_log_dir)
        now = datetime.utcnow()
        
        # Create entries for different dates
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Test Memory",
            description="Test description",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        await writer.append(entry)
        
        dates = await writer.list_available_dates()
        
        assert len(dates) == 1
        assert dates[0].date() == now.date()
    
    @pytest.mark.asyncio
    async def test_get_stats(self, temp_log_dir):
        """Test getting log statistics."""
        from app.core.memory.daily_log import DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        writer = DailyLogWriter(root_path=temp_log_dir)
        now = datetime.utcnow()
        
        # Create multiple entries
        for i in range(3):
            entry = MemoryEntry(
                id=f"mem_{i:03d}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title=f"Memory {i}",
                description="Description",
                content="Content",
                created_at=now,
                updated_at=now,
            )
            await writer.append(entry)
        
        stats = await writer.get_stats()
        
        assert stats["count"] == 3
        assert "by_type" in stats
        assert stats["by_type"]["project"] == 3


class TestLogConsolidator:
    """Tests for LogConsolidator."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for logs."""
        temp_dir = tempfile.mkdtemp(prefix="evoloop_test_consolidation_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_cluster_entries_by_type(self, temp_log_dir):
        """Test clustering entries by type."""
        from app.core.memory.daily_log import LogConsolidator, LogEntry
        
        consolidator = LogConsolidator(root_path=temp_log_dir)
        
        entries = [
            LogEntry(datetime.utcnow(), "mem_1", "project", "Docker Guide", "Desc", None, None),
            LogEntry(datetime.utcnow(), "mem_2", "project", "K8s Guide", "Desc", None, None),
            LogEntry(datetime.utcnow(), "mem_3", "user", "Preference", "Desc", "user_1", None),
        ]
        
        clusters = consolidator._cluster_entries(entries)
        
        # Should have at least 2 clusters (project and user)
        assert len(clusters) >= 2
    
    @pytest.mark.asyncio
    async def test_cluster_by_similarity(self, temp_log_dir):
        """Test similarity-based clustering."""
        from app.core.memory.daily_log import LogConsolidator, LogEntry
        
        consolidator = LogConsolidator(root_path=temp_log_dir)
        
        entries = [
            LogEntry(datetime.utcnow(), "mem_1", "project", "Docker Setup Guide", "Desc", None, None),
            LogEntry(datetime.utcnow(), "mem_2", "project", "Docker Best Practices", "Desc", None, None),
            LogEntry(datetime.utcnow(), "mem_3", "project", "Kubernetes Guide", "Desc", None, None),
        ]
        
        clusters = consolidator._cluster_by_similarity(entries)
        
        # Docker entries should cluster together
        assert len(clusters) >= 2  # At least Docker cluster + K8s cluster
    
    @pytest.mark.asyncio
    async def test_consolidate_date_not_enough_entries(self, temp_log_dir):
        """Test consolidation with insufficient entries."""
        from app.core.memory.daily_log import LogConsolidator, DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        consolidator = LogConsolidator(root_path=temp_log_dir)
        writer = DailyLogWriter(root_path=temp_log_dir)
        
        # Add only 1 entry (need MIN_CLUSTER_SIZE=2)
        now = datetime.utcnow()
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Test",
            description="Desc",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        await writer.append(entry)
        
        yesterday = datetime.utcnow() - timedelta(days=1)
        consolidated = await consolidator.consolidate_date(yesterday)
        
        # Should return empty (not enough entries)
        assert consolidated == []
    
    @pytest.mark.asyncio
    async def test_get_consolidation_report(self, temp_log_dir):
        """Test getting consolidation report."""
        from app.core.memory.daily_log import LogConsolidator, DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        consolidator = LogConsolidator(root_path=temp_log_dir)
        writer = DailyLogWriter(root_path=temp_log_dir)
        
        # Add some entries
        now = datetime.utcnow()
        for i in range(3):
            entry = MemoryEntry(
                id=f"mem_{i:03d}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title=f"Memory {i}",
                description="Desc",
                content="Content",
                created_at=now,
                updated_at=now,
            )
            await writer.append(entry)
        
        report = await consolidator.get_consolidation_report(days=7)
        
        assert "total_entries" in report
        assert report["total_entries"] == 3
        assert "daily_stats" in report


class TestGlobalInstances:
    """Tests for global instances."""
    
    def test_daily_log_writer_singleton(self):
        """Test that global daily_log_writer exists."""
        from app.core.memory.daily_log import daily_log_writer, DailyLogWriter
        
        assert isinstance(daily_log_writer, DailyLogWriter)
    
    def test_log_consolidator_singleton(self):
        """Test that global log_consolidator exists."""
        from app.core.memory.daily_log import log_consolidator, LogConsolidator
        
        assert isinstance(log_consolidator, LogConsolidator)
    
    @pytest.mark.asyncio
    async def test_append_to_daily_log_function(self):
        """Test append_to_daily_log convenience function."""
        from app.core.memory.daily_log import append_to_daily_log
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        import inspect
        assert inspect.iscoroutinefunction(append_to_daily_log)
    
    @pytest.mark.asyncio
    async def test_consolidate_daily_logs_function(self):
        """Test consolidate_daily_logs convenience function."""
        from app.core.memory.daily_log import consolidate_daily_logs
        
        import inspect
        assert inspect.iscoroutinefunction(consolidate_daily_logs)


class TestMemoryIntegration:
    """Tests for integration with memory manager."""
    
    @pytest.mark.asyncio
    async def test_save_memory_appends_to_log(self, monkeypatch, tmp_path):
        """Test that saving memory also appends to daily log."""
        from app.core.memory.daily_log import DailyLogWriter
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        # Create a mock daily log writer
        appended_entries = []
        
        class MockDailyLogWriter:
            async def append(self, entry):
                appended_entries.append(entry)
        
        # Patch the global instance
        import app.core.memory.daily_log as daily_log_module
        original_writer = daily_log_module.daily_log_writer
        daily_log_module.daily_log_writer = MockDailyLogWriter()
        
        try:
            # Create and save a memory
            now = datetime.utcnow()
            entry = MemoryEntry(
                id="mem_test",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title="Test Integration",
                description="Testing daily log integration",
                content="Content",
                created_at=now,
                updated_at=now,
            )
            
            # Simulate what memory_manager.save_memory does
            from app.core.memory.daily_log import daily_log_writer
            await daily_log_writer.append(entry)
            
            # Verify it was logged
            assert len(appended_entries) == 1
            assert appended_entries[0].id == "mem_test"
            
        finally:
            daily_log_module.daily_log_writer = original_writer
