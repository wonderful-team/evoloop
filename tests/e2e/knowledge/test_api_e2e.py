"""
End-to-End HTTP API tests for Knowledge Base.

Tests the complete request/response cycle through FastAPI routes,
using real storage, real FTS, and real file system — no mocks.
"""

from io import BytesIO

import pytest


# ============================================================================
# Collection Management
# ============================================================================

class TestCollectionEndpoints:
    """Test collection management via HTTP API."""

    def test_list_collections_empty(self, client):
        """GET /collections returns empty list when no collections exist."""
        response = client.get("/api/v1/knowledge/collections")
        assert response.status_code == 200
        data = response.json()
        assert data["collections"] == []
        assert "stats" in data
        assert data["stats"]["total_documents"] == 0

    def test_create_collection(self, client):
        """POST /collections/{name} creates a new collection."""
        response = client.post("/api/v1/knowledge/collections/test-coll")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "test-coll" in data["message"]

    def test_list_collections_after_create(self, client):
        """GET /collections includes newly created collection."""
        client.post("/api/v1/knowledge/collections/my-docs")

        response = client.get("/api/v1/knowledge/collections")
        assert response.status_code == 200
        data = response.json()
        assert "my-docs" in data["collections"]
        assert data["stats"]["collections"]["my-docs"]["documents"] == 0


# ============================================================================
# Document Upload
# ============================================================================

class TestDocumentUploadEndpoints:
    """Test document upload via HTTP API."""

    def test_upload_markdown(self, client):
        """POST /upload stores a markdown file and returns path + metadata."""
        content = b"# Hello World\n\nThis is a test document."
        response = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("hello.md", BytesIO(content), "text/markdown")},
            data={"collection": "test-upload", "doc_type": "doc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "path" in data
        assert data["path"].endswith("hello.md")
        assert "document" in data

    def test_upload_with_collection(self, client):
        """Uploaded document appears under the specified collection."""
        content = b"# Project Guide\n\nGuide content here."
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("guide.md", BytesIO(content), "text/markdown")},
            data={"collection": "project-alpha", "doc_type": "guide"},
        )

        response = client.get("/api/v1/knowledge/documents?collection=project-alpha")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any("guide.md" in doc["path"] for doc in data["documents"])


# ============================================================================
# Document Listing
# ============================================================================

class TestDocumentListEndpoints:
    """Test document listing via HTTP API."""

    def test_list_documents(self, client):
        """GET /documents returns total, documents, and collections."""
        # Seed a document
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("doc1.md", BytesIO(b"# Doc 1"), "text/markdown")},
            data={"collection": "list-test", "doc_type": "doc"},
        )

        response = client.get("/api/v1/knowledge/documents")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "documents" in data
        assert "collections" in data
        assert isinstance(data["documents"], list)

    def test_list_with_collection_filter(self, client):
        """Collection filter returns only documents from that collection."""
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("a.md", BytesIO(b"# A"), "text/markdown")},
            data={"collection": "coll-a", "doc_type": "doc"},
        )
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("b.md", BytesIO(b"# B"), "text/markdown")},
            data={"collection": "coll-b", "doc_type": "doc"},
        )

        response = client.get("/api/v1/knowledge/documents?collection=coll-a")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for doc in data["documents"]:
            assert doc["path"].startswith("coll-a/")


# ============================================================================
# Document Reading
# ============================================================================

class TestDocumentReadEndpoints:
    """Test document reading via HTTP API."""

    def test_read_document(self, client):
        """GET /documents/{path} returns content and metadata."""
        lines = "\n".join(f"Line {i}" for i in range(20))
        content = f"# Test Doc\n\n{lines}".encode()
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("readable.md", BytesIO(content), "text/markdown")},
            data={"collection": "read-test", "doc_type": "doc"},
        )

        response = client.get("/api/v1/knowledge/documents/read-test/readable.md")
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "read-test/readable.md"
        assert "content" in data
        assert "metadata" in data
        assert "total_lines" in data
        assert data["total_lines"] >= 20

    def test_read_not_found(self, client):
        """GET /documents/{path} returns 404 for missing document."""
        response = client.get("/api/v1/knowledge/documents/nonexistent/missing.md")
        assert response.status_code == 404

    def test_read_with_pagination(self, client):
        """Offset and limit parameters work correctly."""
        lines = "\n".join(f"Line {i}" for i in range(50))
        content = f"# Paginated\n\n{lines}".encode()
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("paginated.md", BytesIO(content), "text/markdown")},
            data={"collection": "page-test", "doc_type": "doc"},
        )

        response = client.get(
            "/api/v1/knowledge/documents/page-test/paginated.md?offset=10&limit=5"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 10
        assert data["limit"] == 5


# ============================================================================
# Document Deletion
# ============================================================================

class TestDocumentDeleteEndpoints:
    """Test document deletion via HTTP API."""

    def test_delete_document(self, client):
        """DELETE removes document; subsequent GET returns 404."""
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("delete-me.md", BytesIO(b"# Delete Me"), "text/markdown")},
            data={"collection": "del-test", "doc_type": "doc"},
        )

        # Delete
        response = client.delete("/api/v1/knowledge/documents/del-test/delete-me.md")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify gone
        response = client.get("/api/v1/knowledge/documents/del-test/delete-me.md")
        assert response.status_code == 404


# ============================================================================
# FTS Search
# ============================================================================

class TestFTSSearchEndpoints:
    """Test full-text search via HTTP API."""

    def test_fts_search_finds_document(self, client):
        """Uploaded document is findable via FTS search."""
        keyword = "UNIQUE_E2E_KEYWORD_999"
        content = f"# Search Test\n\nThis contains {keyword} for FTS."
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("searchable.md", BytesIO(content.encode()), "text/markdown")},
            data={"collection": "fts-test", "doc_type": "doc"},
        )

        response = client.get(f"/api/v1/knowledge/fts/search?q={keyword}")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert any(keyword in r["title"] or keyword in r["snippet"] for r in data["results"])

    def test_fts_search_with_collection_filter(self, client):
        """Collection filter restricts FTS results."""
        keyword = "SHARED_E2E_WORD"
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("alpha.md", BytesIO(f"# Alpha\n\n{keyword}".encode()), "text/markdown")},
            data={"collection": "fts-alpha", "doc_type": "doc"},
        )
        client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("beta.md", BytesIO(f"# Beta\n\n{keyword}".encode()), "text/markdown")},
            data={"collection": "fts-beta", "doc_type": "doc"},
        )

        response = client.get(f"/api/v1/knowledge/fts/search?q={keyword}&collection=fts-alpha")
        assert response.status_code == 200
        data = response.json()
        for result in data["results"]:
            assert result["collection"] == "fts-alpha"


# ============================================================================
# Full Workflow
# ============================================================================

class TestFullWorkflow:
    """Complete end-to-end workflow tests."""

    def test_complete_document_lifecycle(self, client):
        """
        Full lifecycle: create collection → upload → list → read → search → delete → confirm.
        """
        collection = "e2e-lifecycle"

        # 1. Create collection
        response = client.post(f"/api/v1/knowledge/collections/{collection}")
        assert response.status_code == 200

        # 2. Upload document
        content = b"# Lifecycle Doc\n\nThis document exercises the full API."
        upload_resp = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("lifecycle.md", BytesIO(content), "text/markdown")},
            data={"collection": collection, "doc_type": "doc"},
        )
        assert upload_resp.status_code == 200
        doc_path = upload_resp.json()["path"]

        # 3. List documents in collection
        list_resp = client.get(f"/api/v1/knowledge/documents?collection={collection}")
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] >= 1
        assert any(doc["path"] == doc_path for doc in list_resp.json()["documents"])

        # 4. Read document
        read_resp = client.get(f"/api/v1/knowledge/documents/{doc_path}")
        assert read_resp.status_code == 200
        assert "Lifecycle Doc" in read_resp.json()["content"]

        # 5. FTS search finds it
        search_resp = client.get("/api/v1/knowledge/fts/search?q=exercises&collection=" + collection)
        assert search_resp.status_code == 200
        assert search_resp.json()["total"] >= 1

        # 6. Delete document
        del_resp = client.delete(f"/api/v1/knowledge/documents/{doc_path}")
        assert del_resp.status_code == 200

        # 7. Confirm deletion
        get_resp = client.get(f"/api/v1/knowledge/documents/{doc_path}")
        assert get_resp.status_code == 404

        # 8. Collection still exists but is empty
        coll_resp = client.get("/api/v1/knowledge/collections")
        assert collection in coll_resp.json()["collections"]
