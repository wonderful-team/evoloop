"""
API Extractor
=============

Extracts API endpoint definitions from code files using TreeSitter.
"""

import logging

import tree_sitter

from app.domain.codebase.indexing.extractors.base_extractor import SemanticExtractorBase
from app.domain.codebase.indexing.parsers import parser_registry
from app.domain.codebase.schemas import APIEndpoint

logger = logging.getLogger(__name__)


class APIExtractor(SemanticExtractorBase[APIEndpoint]):
    """
    Extracts API Definitions from code files using TreeSitter.
    Acts as a dispatcher to language-specific providers.
    """

    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

    async def extract(self, file_path: str) -> list[APIEndpoint]:
        """Extract API endpoints from file."""
        # Detect language
        lang_name = self._detect_language(file_path)
        if not lang_name:
            return []

        # Get provider
        provider = self._get_provider(lang_name)
        if not provider:
            return []

        # Get parser
        ext = file_path.split('.')[-1] if '.' in file_path else ''
        parser_info = parser_registry.get_parser(ext)
        if not parser_info:
            return []

        parser, language = parser_info

        # Read and parse
        content = self._read_file(file_path)
        if not content:
            return []

        try:
            tree = parser.parse(bytes(content, "utf8"))
            query_str = provider.get_api_query()
            if not query_str:
                return []

            query = tree_sitter.Query(language, query_str)
            cursor = tree_sitter.QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            entities = []
            for _, captured_nodes in matches:
                results = provider.parse_api_match(captured_nodes, file_path)
                for ep in results:
                    if isinstance(ep, APIEndpoint):
                        if ep.method.lower() in self.HTTP_METHODS:
                            entities.append(ep)

            return entities

        except Exception as e:
            logger.error(f"API Extraction failed for {file_path}: {e}")
            return []

    async def sync_to_graph(self, project_path: str, project_id: int, entities: list[APIEndpoint]):
        """Sync API endpoints to graph.
        
        Args:
            project_path: 项目本地路径（用于获取项目级 graph driver）
            project_id: 项目 ID（用于图数据中的 project_id 属性）
            entities: API endpoint entities to sync
        """
        if not entities:
            return
    
        try:
            from app.infrastructure.database.graph.driver import GraphManager
    
            driver = GraphManager.get_driver(project_path=project_path)
            for ep in entities:
                full_name = f"{ep.method} {ep.path}"
                # 1. Upsert APIEndpoint node
                await driver.upsert_node("APIEndpoint", "full_name", {
                    "full_name": full_name,
                    "project_id": project_id,
                    "method": ep.method,
                    "path": ep.path,
                    "handler": ep.handler_name,
                    "file": ep.file_path
                })
                
                # 2. Link APIEndpoint -> HANDLED_BY -> CodeEntity
                await driver.link_nodes(
                    "APIEndpoint", {"full_name": full_name, "project_id": project_id},
                    "CodeEntity", {"name": ep.handler_name, "project_id": project_id},
                    "HANDLED_BY"
                )

        except Exception as e:
            logger.error(f"Graph Sync for API failed: {e}")


api_extractor = APIExtractor()
