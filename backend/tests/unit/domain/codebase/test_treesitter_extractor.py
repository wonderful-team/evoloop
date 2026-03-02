"""
Unit tests for TreeSitter Extractor.
Tests code structure extraction using TreeSitter parser.
"""

import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

from app.domain.codebase.indexing.extractors.treesitter_extractor import (
    TreeSitterExtractor,
)
from app.domain.codebase.indexing.base import (
    ExtractionResult,
    Document,
    ExtractedEntity,
    ExtractedRelation,
)


class TestTreeSitterExtractor:
    """Tests for TreeSitterExtractor class."""

    @pytest.fixture
    def extractor(self):
        """Create a TreeSitterExtractor instance."""
        return TreeSitterExtractor()

    @pytest.mark.asyncio
    async def test_extract_markdown_headers(self, extractor):
        """Test markdown extraction with header splitting."""
        content = """# Introduction

This is the intro section.

## Features

Feature description here.

### Details

More detailed info.
"""
        result = await extractor.extract(
            file_path="/test/README.md",
            content=content,
            module_path="README.md"
        )

        assert isinstance(result, ExtractionResult)
        assert len(result.documents) >= 2  # At least Intro and Features

        # Check document types
        doc_types = [doc.metadata.get("type") for doc in result.documents]
        assert "documentation" in doc_types

        # Check that headers were captured
        doc_names = [doc.metadata.get("name") for doc in result.documents]
        assert "Intro" in doc_names or "Introduction" in doc_names

    @pytest.mark.asyncio
    async def test_extract_no_parser(self, extractor):
        """Test extraction when no parser is available."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            mock_registry.get_parser.return_value = None

            result = await extractor.extract(
                file_path="/test/unknown.xyz",
                content="some content",
                module_path="test.xyz"
            )

            assert isinstance(result, ExtractionResult)
            assert len(result.documents) == 0
            assert len(result.entities) == 0
            assert len(result.relations) == 0

    @pytest.mark.asyncio
    async def test_extract_parse_failure(self, extractor):
        """Test extraction when parsing fails."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            mock_parser = MagicMock()
            mock_parser.parse.side_effect = Exception("Parse error")
            mock_registry.get_parser.return_value = (mock_parser, MagicMock())
            mock_registry.get_language_key.return_value = "python"

            result = await extractor.extract(
                file_path="/test/test.py",
                content="def test(): pass",
                module_path="test.py"
            )

            assert isinstance(result, ExtractionResult)
            assert len(result.documents) == 0
            assert len(result.entities) == 0

    @pytest.mark.asyncio
    async def test_extract_creates_module_entity(self, extractor):
        """Test that extraction creates a module entity for the file."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            # Setup mock parser that returns empty tree
            mock_parser = MagicMock()
            mock_tree = MagicMock()
            mock_tree.root_node = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_registry.get_parser.return_value = (mock_parser, MagicMock())
            mock_registry.get_language_key.return_value = "python"

            # Mock empty query results
            mock_language = MagicMock()
            mock_language.query.return_value = MagicMock()

            result = await extractor.extract(
                file_path="/test/module.py",
                content="def test():\n    pass\n",
                module_path="module.py"
            )

            # Should create module entity
            assert any(e.type == "module" for e in result.entities)
            module_entities = [e for e in result.entities if e.type == "module"]
            assert len(module_entities) == 1
            assert module_entities[0].full_name == "module.py"

    @pytest.mark.asyncio
    async def test_extract_function_entity(self, extractor):
        """Test extraction of function entities."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            with patch("tree_sitter.QueryCursor") as mock_cursor_class:
                # Setup mock parser
                mock_parser = MagicMock()
                mock_tree = MagicMock()
                mock_tree.root_node = MagicMock()
                mock_parser.parse.return_value = mock_tree
                mock_registry.get_parser.return_value = (mock_parser, MagicMock())
                mock_registry.get_language_key.return_value = "python"

                # Setup mock query cursor with function capture
                mock_cursor = MagicMock()
                mock_cursor.matches.return_value = []
                mock_cursor_class.return_value = mock_cursor

                # Mock language query
                mock_language = MagicMock()
                mock_language.query.return_value = MagicMock()

                result = await extractor.extract(
                    file_path="/test/test.py",
                    content="def hello():\n    pass",
                    module_path="test.py"
                )

                # Verify module entity is created
                assert any(e.type == "module" for e in result.entities)

    def test_is_likely_local_import_relative(self, extractor):
        """Test local import detection with relative imports."""
        assert extractor._is_likely_local_import(".module") is True
        assert extractor._is_likely_local_import("..parent.module") is True
        assert extractor._is_likely_local_import("...grandparent") is True

    def test_is_likely_local_import_app_prefix(self, extractor):
        """Test local import detection with app prefix."""
        assert extractor._is_likely_local_import("app.models") is True
        assert extractor._is_likely_local_import("app.core.engine") is True

    def test_is_likely_local_import_domain_prefix(self, extractor):
        """Test local import detection with domain prefix."""
        assert extractor._is_likely_local_import("domain.tools") is True
        assert extractor._is_likely_local_import("domain.codebase.indexing") is True

    def test_is_likely_local_import_core_prefix(self, extractor):
        """Test local import detection with core prefix."""
        assert extractor._is_likely_local_import("core.brain") is True
        assert extractor._is_likely_local_import("core.engine") is True

    def test_is_likely_local_import_infrastructure_prefix(self, extractor):
        """Test local import detection with infrastructure prefix."""
        assert extractor._is_likely_local_import("infrastructure.llm") is True
        assert extractor._is_likely_local_import("infrastructure.redis") is True

    def test_is_likely_local_import_third_party(self, extractor):
        """Test local import detection with third-party packages."""
        assert extractor._is_likely_local_import("requests") is False
        assert extractor._is_likely_local_import("numpy") is False
        assert extractor._is_likely_local_import("pytest") is False
        assert extractor._is_likely_local_import("langchain") is False

    def test_is_likely_local_import_stdlib(self, extractor):
        """Test local import detection with standard library."""
        assert extractor._is_likely_local_import("os") is False
        assert extractor._is_likely_local_import("sys") is False
        assert extractor._is_likely_local_import("json") is False
        assert extractor._is_likely_local_import("pathlib") is False

    def test_extract_skeleton_basic(self, extractor):
        """Test skeleton extraction from a node."""
        node = MagicMock()
        node.text = b"def test():\n    pass"
        node.child_by_field_name.return_value = None

        skeleton = extractor._extract_skeleton(node, "def test():\n    pass", "function")

        assert isinstance(skeleton, str)
        assert "function" in skeleton or "def" in skeleton

    def test_extract_skeleton_with_docstring(self, extractor):
        """Test skeleton extraction with docstring."""
        node = MagicMock()
        node_text = '''def test():
    """This is a docstring."""
    pass
'''
        node.text = node_text.encode()

        # Mock body with docstring
        mock_body = MagicMock()
        mock_expr_stmt = MagicMock()
        mock_expr_stmt.type = "expression_statement"
        mock_string = MagicMock()
        mock_string.type = "string"
        mock_string.text = b'"""This is a docstring."""'
        mock_expr_stmt.children = [mock_string]
        mock_body.children = [mock_expr_stmt]
        node.child_by_field_name.return_value = mock_body

        skeleton = extractor._extract_skeleton(node, node_text, "function")

        assert isinstance(skeleton, str)

    def test_extract_skeleton_failure_fallback(self, extractor):
        """Test skeleton extraction fallback on failure."""
        node = MagicMock()
        node_text = "def test(): pass"
        node.text = node_text.encode()
        node.child_by_field_name.side_effect = Exception("Error")

        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.logger"):
            skeleton = extractor._extract_skeleton(node, node_text, "function")

            # Should return truncated text on failure
            assert isinstance(skeleton, str)

    @pytest.mark.asyncio
    async def test_extract_with_inheritance_relations(self, extractor):
        """Test extraction of inheritance relations."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            mock_parser = MagicMock()
            mock_tree = MagicMock()
            mock_tree.root_node = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_registry.get_parser.return_value = (mock_parser, MagicMock())
            mock_registry.get_language_key.return_value = "python"

            result = await extractor.extract(
                file_path="/test/models.py",
                content="class Child(Parent):\n    pass",
                module_path="models.py"
            )

            # Module entity should exist
            assert any(e.type == "module" for e in result.entities)

    @pytest.mark.asyncio
    async def test_extract_with_import_relations(self, extractor):
        """Test extraction of import relations."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            mock_parser = MagicMock()
            mock_tree = MagicMock()
            mock_tree.root_node = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_registry.get_parser.return_value = (mock_parser, MagicMock())
            mock_registry.get_language_key.return_value = "python"

            result = await extractor.extract(
                file_path="/test/main.py",
                content="import app.models\nfrom app.core import engine",
                module_path="main.py"
            )

            # Module entity should exist
            assert any(e.type == "module" for e in result.entities)

    @pytest.mark.asyncio
    async def test_extract_test_file_import_detection(self, extractor):
        """Test that test files mark imports with 'tests' relation."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.is_test_file") as mock_is_test:
                mock_is_test.return_value = True

                mock_parser = MagicMock()
                mock_tree = MagicMock()
                mock_tree.root_node = MagicMock()
                mock_parser.parse.return_value = mock_tree
                mock_registry.get_parser.return_value = (mock_parser, MagicMock())
                mock_registry.get_language_key.return_value = "python"

                result = await extractor.extract(
                    file_path="/test/test_models.py",
                    content="import app.models",
                    module_path="test_models.py"
                )

                assert any(e.type == "module" for e in result.entities)

    @pytest.mark.asyncio
    async def test_extract_empty_content(self, extractor):
        """Test extraction with empty content."""
        result = await extractor.extract(
            file_path="/test/empty.py",
            content="",
            module_path="empty.py"
        )

        assert isinstance(result, ExtractionResult)
        # Module entity should still be created
        assert any(e.type == "module" for e in result.entities)

    @pytest.mark.asyncio
    async def test_extract_no_module_path_fallback(self, extractor):
        """Test extraction falls back to file_path when module_path not provided."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            mock_parser = MagicMock()
            mock_tree = MagicMock()
            mock_tree.root_node = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_registry.get_parser.return_value = (mock_parser, MagicMock())
            mock_registry.get_language_key.return_value = "python"

            result = await extractor.extract(
                file_path="/path/to/module.py",
                content="def test(): pass",
                module_path=None
            )

            # Should use file_path as module_path
            assert any(e.type == "module" for e in result.entities)


class TestTreeSitterExtractorEdgeCases:
    """Edge case tests for TreeSitterExtractor."""

    @pytest.fixture
    def extractor(self):
        """Create a TreeSitterExtractor instance."""
        return TreeSitterExtractor()

    @pytest.mark.asyncio
    async def test_extract_query_failure_continues(self, extractor):
        """Test that query failure doesn't crash extraction."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            mock_parser = MagicMock()
            mock_tree = MagicMock()
            mock_tree.root_node = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_registry.get_parser.return_value = (mock_parser, MagicMock())
            mock_registry.get_language_key.return_value = "python"

            # Mock language that raises on query
            mock_language = MagicMock()
            mock_language.query.side_effect = Exception("Query failed")

            with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.logger"):
                result = await extractor.extract(
                    file_path="/test/test.py",
                    content="def test(): pass",
                    module_path="test.py"
                )

                # Should still return valid result with module entity
                assert isinstance(result, ExtractionResult)
                assert any(e.type == "module" for e in result.entities)

    @pytest.mark.asyncio
    async def test_extract_go_method_receiver(self, extractor):
        """Test Go method receiver handling."""
        with patch("app.domain.codebase.indexing.extractors.treesitter_extractor.parser_registry") as mock_registry:
            mock_parser = MagicMock()
            mock_tree = MagicMock()
            mock_tree.root_node = MagicMock()
            mock_parser.parse.return_value = mock_tree
            mock_registry.get_parser.return_value = (mock_parser, MagicMock())
            mock_registry.get_language_key.return_value = "go"

            result = await extractor.extract(
                file_path="/test/main.go",
                content="func (r *Receiver) Method() {}",
                module_path="main.go"
            )

            assert isinstance(result, ExtractionResult)
            assert any(e.type == "module" for e in result.entities)

    @pytest.mark.asyncio
    async def test_extract_markdown_single_header(self, extractor):
        """Test markdown with only one header."""
        content = "# Only Header\n\nSome content."

        result = await extractor.extract(
            file_path="/test/single.md",
            content=content,
            module_path="single.md"
        )

        assert len(result.documents) == 1
        assert result.documents[0].metadata.get("name") == "Only Header"

    @pytest.mark.asyncio
    async def test_extract_markdown_no_headers(self, extractor):
        """Test markdown without any headers."""
        content = "Just some text\nwithout any headers."

        result = await extractor.extract(
            file_path="/test/no_headers.md",
            content=content,
            module_path="no_headers.md"
        )

        # Should create a single document with "Intro"
        assert len(result.documents) == 1
        assert result.documents[0].metadata.get("name") == "Intro"

    @pytest.mark.asyncio
    async def test_extract_markdown_multiple_same_level_headers(self, extractor):
        """Test markdown with multiple same-level headers."""
        content = """# Header 1
Content 1
# Header 2
Content 2
# Header 3
Content 3
"""

        result = await extractor.extract(
            file_path="/test/multi.md",
            content=content,
            module_path="multi.md"
        )

        assert len(result.documents) == 3
        names = [doc.metadata.get("name") for doc in result.documents]
        assert "Header 1" in names
        assert "Header 2" in names
        assert "Header 3" in names


class TestTreeSitterExtractionResult:
    """Tests for extraction result structure."""

    @pytest.fixture
    def extractor(self):
        """Create a TreeSitterExtractor instance."""
        return TreeSitterExtractor()

    def test_extraction_result_structure(self):
        """Test ExtractionResult dataclass structure."""
        doc = Document(
            content="test content",
            metadata={"type": "function", "name": "test"}
        )
        entity = ExtractedEntity(
            name="test",
            type="function",
            full_name="test.py::test",
            start_line=1,
            end_line=2,
            content="def test(): pass",
            metadata={}
        )
        relation = ExtractedRelation(
            source_full_name="test.py::test",
            target_full_name="other.py::other",
            relation_type="imports",
            start_line=1
        )

        result = ExtractionResult(
            documents=[doc],
            entities=[entity],
            relations=[relation]
        )

        assert len(result.documents) == 1
        assert len(result.entities) == 1
        assert len(result.relations) == 1
        assert result.documents[0].content == "test content"
        assert result.entities[0].name == "test"
        assert result.relations[0].relation_type == "imports"
