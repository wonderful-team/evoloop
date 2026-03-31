"""
Tests for app.utils.diff module.
"""

import pytest
import tempfile
import os

from app.utils.diff import (
    DiffTracker,
    compute_text_diff,
    get_diff_stats,
    diff_tracker,
)


class TestDiffTracker:
    """Test cases for DiffTracker class."""

    def test_capture_and_compute_diff_edit(self):
        """Test capturing snapshot and computing diff for edited file."""
        tracker = DiffTracker()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\nline3\n")
            temp_path = f.name
        
        try:
            # Capture snapshot
            tracker.capture_snapshot(temp_path, thread_id="test_1")
            assert tracker.has_snapshot(temp_path, "test_1")
            
            # Modify file
            with open(temp_path, 'w') as f:
                f.write("line1\nline2_modified\nline3\n")
            
            # Compute diff
            operation, diff, original = tracker.compute_diff(temp_path, thread_id="test_1")
            
            assert operation == "EDIT"
            assert "line2_modified" in diff
            assert "line2\n" in original
            assert not tracker.has_snapshot(temp_path, "test_1")  # Snapshot consumed
        finally:
            os.unlink(temp_path)
    
    def test_capture_and_compute_diff_add(self):
        """Test diff for newly created file."""
        tracker = DiffTracker()
        temp_path = tempfile.mktemp(suffix='.py')
        
        try:
            # Capture snapshot (file doesn't exist yet)
            tracker.capture_snapshot(temp_path, thread_id="test_1")
            
            # Create file
            with open(temp_path, 'w') as f:
                f.write("new content\n")
            
            operation, diff, original = tracker.compute_diff(temp_path, thread_id="test_1")
            
            assert operation == "ADD"
            assert diff != ""
            assert original is None
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_capture_and_compute_diff_delete(self):
        """Test diff for deleted file."""
        tracker = DiffTracker()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("content to delete\n")
            temp_path = f.name
        
        try:
            tracker.capture_snapshot(temp_path, thread_id="test_1")
            
            # Delete file
            os.unlink(temp_path)
            
            operation, diff, original = tracker.compute_diff(temp_path, thread_id="test_1")
            
            assert operation == "DELETE"
            assert "content to delete" in original
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_no_change(self):
        """Test when file hasn't changed."""
        tracker = DiffTracker()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("unchanged content\n")
            temp_path = f.name
        
        try:
            tracker.capture_snapshot(temp_path, thread_id="test_1")
            
            # Don't modify
            operation, diff, original = tracker.compute_diff(temp_path, thread_id="test_1")
            
            assert operation == ""
            assert diff == ""
            assert original is None
        finally:
            os.unlink(temp_path)
    
    def test_no_snapshot(self):
        """Test computing diff without snapshot."""
        tracker = DiffTracker()
        
        operation, diff, original = tracker.compute_diff("/nonexistent/path.py", thread_id="test_1")
        
        assert operation == ""
        assert diff == ""
        assert original is None
    
    def test_thread_isolation(self):
        """Test that different threads don't interfere."""
        tracker = DiffTracker()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("content\n")
            temp_path = f.name
        
        try:
            tracker.capture_snapshot(temp_path, thread_id="thread_a")
            tracker.capture_snapshot(temp_path, thread_id="thread_b")
            
            assert tracker.get_snapshot_count("thread_a") == 1
            assert tracker.get_snapshot_count("thread_b") == 1
            assert tracker.get_snapshot_count() == 2
            
            # Clear only thread_a
            tracker.clear("thread_a")
            assert tracker.get_snapshot_count("thread_a") == 0
            assert tracker.get_snapshot_count("thread_b") == 1
        finally:
            os.unlink(temp_path)
    
    def test_clear_all(self):
        """Test clearing all snapshots."""
        tracker = DiffTracker()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            temp_path = f.name
        
        try:
            tracker.capture_snapshot(temp_path, thread_id="thread_a")
            tracker.capture_snapshot(temp_path, thread_id="thread_b")
            
            tracker.clear()
            
            assert tracker.get_snapshot_count() == 0
        finally:
            os.unlink(temp_path)
    
    def test_global_singleton(self):
        """Test the global diff_tracker singleton."""
        from app.utils.diff import diff_tracker as dt2
        assert diff_tracker is dt2


class TestComputeTextDiff:
    """Test cases for compute_text_diff function."""

    def test_basic_diff(self):
        """Test basic text diff."""
        old = "hello\nworld"
        new = "hello\npython"
        
        diff = compute_text_diff(old, new)
        
        assert "-world" in diff
        assert "+python" in diff
    
    def test_addition_only(self):
        """Test diff with only additions."""
        old = "line1"
        new = "line1\nline2"
        
        diff = compute_text_diff(old, new)
        
        assert "+line2" in diff
    
    def test_deletion_only(self):
        """Test diff with only deletions."""
        old = "line1\nline2"
        new = "line1"
        
        diff = compute_text_diff(old, new)
        
        assert "-line2" in diff
    
    def test_empty_strings(self):
        """Test diff with empty strings."""
        diff = compute_text_diff("", "new content")
        
        assert "+new content" in diff
    
    def test_custom_labels(self):
        """Test diff with custom file labels."""
        diff = compute_text_diff("a", "b", old_label="original.txt", new_label="modified.txt")
        
        assert "original.txt" in diff
        assert "modified.txt" in diff
    
    def test_context_lines(self):
        """Test diff with different context lines."""
        old = "\n".join([f"line{i}" for i in range(10)])
        new = old.replace("line5", "modified")
        
        diff = compute_text_diff(old, new, context_lines=1)
        # With 1 context line, diff should be shorter
        assert "modified" in diff


class TestGetDiffStats:
    """Test cases for get_diff_stats function."""

    def test_added_lines(self):
        """Test stats for added lines."""
        old = "line1\nline2"
        new = "line1\nline2\nline3"
        
        stats = get_diff_stats(old, new)
        
        assert stats["lines_added"] == 1
        assert stats["lines_removed"] == 0
        assert stats["lines_unchanged"] == 2
    
    def test_removed_lines(self):
        """Test stats for removed lines."""
        old = "line1\nline2\nline3"
        new = "line1\nline3"
        
        stats = get_diff_stats(old, new)
        
        assert stats["lines_added"] == 0
        assert stats["lines_removed"] == 1
        assert stats["lines_unchanged"] == 2
    
    def test_replaced_lines(self):
        """Test stats for replaced lines."""
        old = "line1\nold_line\nline3"
        new = "line1\nnew_line\nline3"
        
        stats = get_diff_stats(old, new)
        
        assert stats["lines_added"] == 1
        assert stats["lines_removed"] == 1
        assert stats["lines_unchanged"] == 2
    
    def test_unchanged_content(self):
        """Test stats for identical content."""
        old = "same\ncontent"
        new = "same\ncontent"
        
        stats = get_diff_stats(old, new)
        
        assert stats["lines_added"] == 0
        assert stats["lines_removed"] == 0
        assert stats["lines_unchanged"] == 2
    
    def test_chars_changed(self):
        """Test character change count."""
        old = "hello"
        new = "world"
        
        stats = get_diff_stats(old, new)
        
        assert stats["chars_changed"] > 0
