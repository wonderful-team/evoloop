"""
API Extractor
=============

Extracts API endpoint definitions from code files using TreeSitter.
"""

import logging
from dataclasses import dataclass

import tree_sitter

from pydantic import BaseModel

from app.domain.codebase.indexing.parsers import parser_registry
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class APIEndpoint(DynamicBaseModel):
    method: str
    path: str
    handler_name: str
    file_path: str
    line_number: int


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

            endpoints = []
            for _, captured_nodes in matches:
                results = provider.parse_api_match(captured_nodes, file_path)
                for ep in results:
                    if isinstance(ep, APIEndpoint):
                        if ep.method.lower() in self.HTTP_METHODS:
                            endpoints.append(ep)

            return endpoints

        except Exception as e:
            logger.error(f"API Extraction failed for {file_path}: {e}")
            return []

    async def sync_to_graph(self, project_id: int, endpoints: list[APIEndpoint]):
        """Sync API endpoints to Neo4j graph."""
        if not endpoints:
            return

        try:
            from app.infrastructure.database.graph.driver import get_graph_db

            driver = await get_graph_db()
            async with driver.session() as session:
                for ep in endpoints:
                    full_name = f"{ep.method} {ep.path}"
                    await session.run(
                        """
                        MERGE (e:APIEndpoint {full_name: $id, project_id: $pid})
                        SET e.method = $method, e.path = $path, e.handler = $handler, e.file = $file
                        WITH e
                        MATCH (fn:CodeEntity {name: $handler, project_id: $pid})
                        MERGE (e)-[:HANDLED_BY]->(fn)
                    """,
                        id=full_name,
                        pid=project_id,
                        method=ep.method,
                        path=ep.path,
                        handler=ep.handler_name,
                        file=ep.file_path,
                    )

        except Exception as e:
            logger.error(f"Graph Sync for API failed: {e}")


api_extractor = APIExtractor()
