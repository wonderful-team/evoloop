import logging
import os  # Added import
from dataclasses import dataclass

import tree_sitter

from app.constants import SEMANTIC_LANGUAGE_MAP
from app.domain.codebase.indexing.parsers import parser_registry
from app.utils.file import read_file_content

from .sem_provider import LanguageSemanticProvider

logger = logging.getLogger(__name__)


@dataclass
class APIEndpoint:
    method: str
    path: str
    handler_name: str
    file_path: str
    line_number: int


class APIExtractor:
    """
    Extracts API Definitions from code files using TreeSitter.
    Acts as a dispatcher to language-specific providers.
    """

    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

    def __init__(self):
        # Use shared provider registry instead of creating own instances
        from .provider_registry import semantic_provider_registry
        self._registry = semantic_provider_registry

    def _get_provider(self, lang_name: str) -> LanguageSemanticProvider | None:
        """Get provider from shared registry."""
        return self._registry.get(lang_name)

    async def extract(self, file_path: str) -> list[APIEndpoint]:
        ext = os.path.splitext(file_path)[1].lower()

        # Find the language for this extension
        lang_name = None
        for name, exts in SEMANTIC_LANGUAGE_MAP.items():
            if ext in exts:
                lang_name = name
                break

        provider = self._get_provider(lang_name) if lang_name else None
        if not provider:
            return []
        parser_info = parser_registry.get_parser(ext.lstrip("."))
        if not parser_info:
            return []

        parser, language = parser_info

        try:
            content, _ = read_file_content(file_path)
            if not content:
                return []

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
