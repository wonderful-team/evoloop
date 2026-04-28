"""
Tests for knowledge base agent tools.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.knowledge.tools.read import kb_read
from app.domain.knowledge.tools.search import kb_search
from app.domain.knowledge.tools.list import kb_list


class TestKBReadTool:
    """Tests for kb_read tool."""
    
    @pytest.mark.asyncio
    async def test_read_document_success(self):
        """Test successful document read."""
        mock_result = {
            "content": "Line 1\nLine 2\nLine 3",
            "offset": 0,
            "limit": 100,
            "total_lines": 3,
            "has_more": False
        }
        
        with patch("app.domain.knowledge.tools.read.KnowledgeStoreService") as MockStore:
            store = MagicMock()
            store.read_document.return_value = mock_result
            MockStore.return_value = store
            
            result = await kb_read.ainvoke({"path": "test.md", "offset": 0, "limit": 100})
            
            assert "test.md" in result
            assert "Line 1" in result
    
    @pytest.mark.asyncio
    async def test_read_document_not_found(self):
        """Test reading non-existent document."""
        with patch("app.domain.knowledge.tools.read.KnowledgeStoreService") as MockStore:
            store = MagicMock()
            store.read_document.side_effect = FileNotFoundError("Not found")
            MockStore.return_value = store
            
            result = await kb_read.ainvoke({"path": "nonexistent.md"})
            
            assert "not found" in result.lower()


class TestKBSearchTool:
    """Tests for kb_search tool."""
    
    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful search."""
        mock_docs = [
            {"path": "doc1.md", "title": "Doc 1"},
            {"path": "doc2.md", "title": "Doc 2"}
        ]
        
        with patch("app.domain.knowledge.tools.search.KnowledgeStoreService") as MockStore:
            store = MagicMock()
            store.list_documents.return_value = mock_docs
            # Mock document read to return content with search term
            store.read_document.return_value = {
                "content": "This contains the search term",
                "offset": 0,
                "limit": 100,
                "total_lines": 1,
                "has_more": False
            }
            MockStore.return_value = store
            
            result = await kb_search.ainvoke({"pattern": "search term"})
            
            assert "search term" in result
    
    @pytest.mark.asyncio
    async def test_search_no_results(self):
        """Test search with no results."""
        with patch("app.domain.knowledge.tools.search.KnowledgeStoreService") as MockStore:
            store = MagicMock()
            store.list_documents.return_value = []
            MockStore.return_value = store
            
            result = await kb_search.ainvoke({"pattern": "nonexistent"})
            
            assert "No matches" in result or "no matches" in result.lower()


class TestKBListTool:
    """Tests for kb_list tool."""
    
    @pytest.mark.asyncio
    async def test_list_documents(self):
        """Test listing documents."""
        from app.domain.knowledge.schemas import DocumentListItem
        mock_docs = [
            DocumentListItem(
                path="project/doc1.md",
                title="Doc 1",
                size_bytes=100,
                modified_at="2024-01-01T00:00:00",
                has_metadata=True,
                tags=[],
            ),
            DocumentListItem(
                path="project/doc2.md",
                title="Doc 2",
                size_bytes=200,
                modified_at="2024-01-02T00:00:00",
                has_metadata=True,
                tags=[],
            )
        ]
        
        with patch("app.domain.knowledge.tools.list.KnowledgeStoreService") as MockStore:
            store = MagicMock()
            store.list_documents.return_value = mock_docs
            MockStore.return_value = store
            
            result = await kb_list.ainvoke({"collection": "project"})
            
            assert "Doc 1" in result
            assert "Doc 2" in result
    
    @pytest.mark.asyncio
    async def test_list_empty(self):
        """Test listing with no documents."""
        with patch("app.domain.knowledge.tools.list.KnowledgeStoreService") as MockStore:
            store = MagicMock()
            store.list_documents.return_value = []
            MockStore.return_value = store
            
            result = await kb_list.ainvoke({})
            
            assert "No documents" in result


class TestToolIntegration:
    """Integration tests for knowledge tools."""
    
    @pytest.mark.asyncio
    async def test_workflow_search_then_read(self):
        """Test typical workflow: search then read."""
        # This would be a more comprehensive integration test
        # that tests the interaction between tools
        pass
