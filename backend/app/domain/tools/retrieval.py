import asyncio
import logging

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class ToolRetriever:
    """
    Manages semantic retrieval of tools to avoid context window saturation.
    Uses in-memory vector storage for ephemeral tool instances.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        # self.embedder = OpenAIEmbedder() # Moved to PGToolRetriever
        # self.tools: List[BaseTool] = [] # Deprecated
        # self.embeddings: List[List[float]] = [] # Deprecated
        # self._indexed_names = set() # Deprecated

        self.tools_map: dict[str, BaseTool] = {}  # Local runtime cache
        self._lock = asyncio.Lock()

    @staticmethod
    def _build_signature(tool: BaseTool) -> str:
        """
        Auto-generate a semantic signature from tool metadata.
        Replaces hardcoded keyword boosts with schema-driven extraction.
        """
        parts = [f"Tool: {tool.name}", f"Description: {tool.description or ''}"]

        # Extract parameter names from args_schema for richer semantic matching
        if hasattr(tool, "args_schema") and tool.args_schema:
            try:
                field_names = list(tool.args_schema.model_fields.keys())
                if field_names:
                    parts.append(f"Parameters: {', '.join(field_names)}")

                # Extract field descriptions for even richer signatures
                field_descs = []
                for fname, finfo in tool.args_schema.model_fields.items():
                    if finfo.description:
                        field_descs.append(f"{fname}: {finfo.description}")
                if field_descs:
                    parts.append(f"Parameter Details: {'; '.join(field_descs[:5])}")
            except Exception:
                pass

        return "\n".join(parts)

    async def index_tools(self, tools: list[BaseTool]):
        """
        Index a list of tools. Idempotent based on tool name.
        Migrated to PGToolRetriever for scalability.
        """
        from app.domain.tools.vector_store import pg_tool_retriever

        async with self._lock:
            for tool in tools:
                if tool.name in self.tools_map:
                    continue

                self.tools_map[tool.name] = tool

                # Auto-generate semantic signature from tool metadata
                signature = self._build_signature(tool)

                # Async Indexing in DB
                await pg_tool_retriever.index_tool(tool.name, tool.description, signature)

            logger.info(f"Tool Retrieval Index Updated (PG). Total Tools Helper Map: {len(self.tools_map)}")

    async def retrieve(self, query: str, k: int = 10) -> list[BaseTool]:
        """
        Get top-k relevant tools for the query.
        """
        from app.domain.tools.vector_store import pg_tool_retriever

        try:
            tool_records = await pg_tool_retriever.search_tools(query, k)

            results = []
            for record in tool_records:
                name = record["name"]
                # Look up the actual executable tool instance
                if name in self.tools_map:
                    results.append(self.tools_map[name])
                else:
                    logger.warning(f"Tool {name} found in Index but not in local runtime map.")

            return results

        except Exception as e:
            logger.error(f"Tool retrieval error: {e}")
            return []


# Global Instance
tool_retriever = ToolRetriever()
