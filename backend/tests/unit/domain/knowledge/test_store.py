"""
Tests for KnowledgeStoreService.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from app.domain.knowledge.services.store import KnowledgeStoreService
from app.domain.knowledge.models import MarkdownDocument, DocumentMetadata


class TestKnowledgeStoreService:
    """Tests for KnowledgeStoreService."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def store(self, temp_dir):
        """Create a store instance with temp directory."""
        return KnowledgeStoreService(base_path=temp_dir)
    
    @pytest.fixture
    def sample_document(self):
        """Create a sample document."""
        return MarkdownDocument(
            content="# Test Document\n\nThis is a test.",
            source="test.md",
            mime_type="text/markdown",
            metadata={"title": "Test Document"}
        )
    
    def test_initialization(self, temp_dir):
        """Test store initialization creates directories."""
        store = KnowledgeStoreService(base_path=temp_dir)
        
        assert (Path(temp_dir) / "raw").exists()
        assert (Path(temp_dir) / "meta").exists()
        assert (Path(temp_dir) / "temp").exists()
    
    def test_save_document(self, store, sample_document):
        """Test saving a document."""
        metadata = DocumentMetadata(
            source_file="test.md",
            source_mime_type="text/markdown",
            file_size_bytes=100,
            extracted_at=datetime.utcnow()
        )
        
        path = store.save_document(
            document=sample_document,
            metadata=metadata,
            project="test-project",
            path="docs/test.md"
        )
        
        assert path == "test-project/docs/test.md"
        assert (store.base_path / "raw" / "test-project" / "docs" / "test.md").exists()
        assert (store.base_path / "meta" / "test-project" / "docs" / "test.md.json").exists()
    
    def test_read_document(self, store, sample_document):
        """Test reading a document."""
        metadata = DocumentMetadata(
            source_file="test.md",
            source_mime_type="text/markdown",
            file_size_bytes=100,
            extracted_at=datetime.utcnow()
        )
        
        store.save_document(
            document=sample_document,
            metadata=metadata,
            project="test-project"
        )
        
        result = store.read_document("test-project/test.md")
        
        assert result["content"] == "# Test Document\n\nThis is a test."
        assert result["path"] == "test-project/test.md"
        assert result["encoding"] == "utf-8"
    
    def test_read_document_with_pagination(self, store):
        """Test reading a document with pagination."""
        doc = MarkdownDocument(
            content="Line 1\nLine 2\nLine 3\nLine 4\nLine 5",
            source="test.txt",
            mime_type="text/plain"
        )
        
        store.save_document(doc, project="test")
        
        # Read first 2 lines
        result = store.read_document("test/test.md", offset=0, limit=2)
        assert "Line 1" in result["content"]
        assert "Line 2" in result["content"]
        assert result["has_more"] is True
        
        # Read next 2 lines
        result = store.read_document("test/test.md", offset=2, limit=2)
        assert "Line 3" in result["content"]
        assert "Line 4" in result["content"]
    
    def test_delete_document(self, store, sample_document):
        """Test deleting a document."""
        metadata = DocumentMetadata(
            source_file="test.md",
            source_mime_type="text/markdown",
            file_size_bytes=100,
            extracted_at=datetime.utcnow()
        )
        
        store.save_document(sample_document, metadata, project="test")
        
        deleted = store.delete_document("test/test.md")
        
        assert deleted is True
        assert not (store.base_path / "raw" / "test" / "test.md").exists()
    
    def test_list_documents(self, store):
        """Test listing documents."""
        # Create multiple documents
        for i in range(3):
            doc = MarkdownDocument(
                content=f"Document {i}",
                source=f"doc{i}.md",
                mime_type="text/markdown"
            )
            store.save_document(doc, project="test-project")
        
        documents = store.list_documents("test-project")
        
        assert len(documents) == 3
        assert all("path" in doc for doc in documents)
        assert all("size_bytes" in doc for doc in documents)
    
    def test_list_projects(self, store):
        """Test listing projects."""
        # Create documents in different projects
        for project in ["project-a", "project-b", "project-c"]:
            doc = MarkdownDocument(
                content=f"Doc for {project}",
                source="test.md",
                mime_type="text/markdown"
            )
            store.save_document(doc, project=project)
        
        projects = store.list_projects()
        
        assert len(projects) == 3
        assert "project-a" in projects
        assert "project-b" in projects
        assert "project-c" in projects
    
    def test_create_project(self, store):
        """Test creating a project."""
        path = store.create_project("new-project")
        
        assert path.exists()
        assert (store.base_path / "raw" / "new-project").exists()
        assert (store.base_path / "meta" / "new-project").exists()
    
    def test_delete_project(self, store):
        """Test deleting a project."""
        store.create_project("delete-me")
        
        deleted = store.delete_project("delete-me")
        
        assert deleted is True
        assert not (store.base_path / "raw" / "delete-me").exists()
    
    def test_get_stats(self, store):
        """Test getting statistics."""
        # Create some documents
        for i in range(3):
            doc = MarkdownDocument(
                content=f"Content {i}",
                source=f"doc{i}.md",
                mime_type="text/markdown"
            )
            store.save_document(doc, project="stats-test")
        
        stats = store.get_stats()
        
        assert stats["total_documents"] == 3
        assert stats["total_size_bytes"] > 0
        assert "stats-test" in stats["projects"]
    
    def test_read_nonexistent_document(self, store):
        """Test reading a document that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            store.read_document("nonexistent/project/doc.md")
