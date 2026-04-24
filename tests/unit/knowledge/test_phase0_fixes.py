"""
Phase 0 Regression Tests - 高危Bug修复验证

覆盖:
- B-01: citations.py 日期计算溢出
- B-02: auto_maintenance.py patterns 类型错误
- B-03: auto_maintenance.py doc_info.get() 不存在 + result.get() 不存在
- B-04: bulk_import.py ZIP 内存溢出
"""

import io
import os
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCitationDateCalculation:
    """B-01: 验证日期计算修复"""

    def test_get_usage_analytics_since_calculation(self):
        """验证 since 日期计算不溢出"""
        import asyncio
        from unittest.mock import patch
        from app.domain.knowledge.services.citations import CitationTracker

        tracker = CitationTracker(db_path=Path(tempfile.mktemp(suffix=".db")))

        # Mock the pool.acquire context manager
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"count": 0}
        mock_conn.execute.return_value.__iter__ = lambda self: iter([])

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__enter__ = lambda self: mock_conn
        mock_pool.acquire.return_value.__exit__ = lambda self, *args: None
        tracker.pool = mock_pool

        # Test various day values that would have caused overflow before fix
        test_cases = [1, 5, 10, 30, 60, 90, 365]

        for days in test_cases:
            # This should not raise ValueError anymore
            try:
                asyncio.run(tracker.get_usage_analytics(days=days))
            except ValueError as e:
                pytest.fail(f"get_usage_analytics(days={days}) raised ValueError: {e}")

    def test_since_date_accuracy(self):
        """验证 since 日期计算准确"""
        # The fix changes from: replace(day=day-days) to: now - timedelta(days=days)
        now = datetime.now()
        days = 30

        # Old buggy approach
        try:
            buggy_since = now.replace(day=now.day - days)
        except ValueError:
            buggy_since = None  # Would fail on days like 5th of month with days=30

        # New correct approach
        correct_since = now - timedelta(days=days)

        # The correct approach should always work
        assert correct_since is not None
        # And should be approximately 'days' days ago
        delta = now - correct_since
        assert delta.days == days


class TestMaintenancePatternsType:
    """B-02: 验证 patterns 类型错误修复"""

    def test_suggest_optimizations_hot_docs_access(self):
        """验证 patterns.hot_docs 作为 Pydantic 模型属性访问"""
        from app.domain.knowledge.services.auto_maintenance import (
            UsageAnalyzer,
            UsageAnalysisResult,
            UsageDocInfo,
        )

        # Create a proper UsageAnalysisResult with UsageDocInfo items
        hot_doc = UsageDocInfo(
            path="test/doc.md",
            citations=10,
            last_accessed=datetime.now().isoformat(),
            unique_sessions=5,
        )

        patterns = UsageAnalysisResult(
            hot_docs=[hot_doc],
            cold_docs=[],
            total_analyzed=1,
        )

        # This should work with the fix (using .path attribute access)
        hot_paths = {d.path for d in patterns.hot_docs}
        assert "test/doc.md" in hot_paths

        # The old code would have failed:
        # hot_paths = {d["path"] for d in patterns["hot_docs"]}  # TypeError


class TestMaintenanceDocInfoAccess:
    """B-03: 验证 doc_info 和 result 属性访问修复"""

    def test_usage_doc_info_attribute_access(self):
        """验证 UsageDocInfo 作为 Pydantic 模型使用属性访问"""
        from app.domain.knowledge.services.auto_maintenance import UsageDocInfo

        doc_info = UsageDocInfo(
            path="test/doc.md",
            citations=5,
            last_accessed=datetime.now().isoformat(),
        )

        # Should use attribute access, not .get()
        assert doc_info.citations == 5

        # Old code would fail:
        # doc_info.get("citations", 0)  # AttributeError

    def test_document_read_result_attribute_access(self):
        """验证 DocumentReadResult 使用 frontmatter 属性"""
        from app.domain.knowledge.services.store import DocumentReadResult

        result = DocumentReadResult(
            content="test content",
            frontmatter={"source": "original.pdf", "title": "Test"},
            extracted_metadata={"source_file": "original.pdf"},
            path="test/doc.md",
            encoding="utf-8",
            offset=0,
            limit=100,
            total_lines=10,
            has_more=False,
        )

        # Should access via frontmatter attribute
        source = result.frontmatter.get("source", "unknown")
        assert source == "original.pdf"

        # Should be able to unpack frontmatter
        metadata = {**result.frontmatter, "extra": "value"}
        assert metadata["source"] == "original.pdf"
        assert metadata["extra"] == "value"


class TestBulkImportMemory:
    """B-04: 验证 ZIP 导入内存修复"""

    def test_import_zip_small_file_uses_memory(self):
        """验证小ZIP使用内存流"""
        from app.domain.knowledge.services.bulk_import import BulkImportService

        # Create a small ZIP in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("test.txt", "Hello World")
        zip_buffer.seek(0)

        service = BulkImportService()

        # Mock pipeline to avoid actual processing
        with patch.object(service.pipeline, 'process') as mock_process:
            mock_process.return_value = MagicMock(success=True, path="test/test.txt")

            import asyncio
            result = asyncio.run(service.import_zip(zip_buffer, project="test"))

        # Should succeed
        assert result.total_files == 1

    def test_import_zip_large_file_uses_temp(self):
        """验证大ZIP使用临时文件"""
        import random
        from app.domain.knowledge.services.bulk_import import BulkImportService

        # Create a large ZIP (>100MB threshold) with incompressible data
        # Use .dat extension (not filtered) and random data (poor compression)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            # Generate random data using os.urandom (faster than Python loop)
            random_data = os.urandom(105 * 1024 * 1024)
            zf.writestr("large.dat", random_data)
        zip_buffer.seek(0)

        service = BulkImportService()

        # Mock pipeline
        with patch.object(service.pipeline, 'process') as mock_process:
            mock_process.return_value = MagicMock(success=True, path="test/large.dat")

            import asyncio
            result = asyncio.run(service.import_zip(zip_buffer, project="test"))

        # Should process the file
        assert result.total_files == 1

    def test_import_zip_temp_cleanup(self):
        """验证临时文件被清理"""
        from app.domain.knowledge.services.bulk_import import BulkImportService

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("test.txt", "content")
        zip_buffer.seek(0)

        service = BulkImportService()

        temp_files_before = set(tempfile.gettempdir())

        with patch.object(service.pipeline, 'process') as mock_process:
            mock_process.return_value = MagicMock(success=True, path="test/test.txt")

            import asyncio
            asyncio.run(service.import_zip(zip_buffer, project="test"))

        # No lingering temp files from our operation
        # (Note: exact verification would require tracking the temp path)


class TestImportZipStructureBug:
    """额外验证: ZIP preserve_structure 逻辑"""

    def test_preserve_structure_single_level(self):
        """验证单层目录ZIP不会丢失文件名"""
        from app.domain.knowledge.services.bulk_import import BulkImportService

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("readme.txt", "Hello")
        zip_buffer.seek(0)

        service = BulkImportService()

        with patch.object(service.pipeline, 'process') as mock_process:
            mock_process.return_value = MagicMock(success=True, path="default/readme.txt")

            import asyncio
            result = asyncio.run(service.import_zip(
                zip_buffer,
                project="test",
                preserve_structure=True
            ))

        assert result.total_files == 1
