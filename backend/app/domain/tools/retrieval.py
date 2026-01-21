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

    async def index_tools(self, tools: list[BaseTool]):
        """
        Index a list of tools. Idempotent based on tool name.
        Migrated to PGToolRetriever for scalability.
        """
        from app.domain.tools.vector_store import pg_tool_retriever

        # We still keep a small in-memory map of ACTUAL tool objects
        # because PG only stores metadata, but we need to return Executable Tool Objects.
        # However, for distributed systems, tools should be re-instantiated or retrieved from registry by name.
        # Currently, 'tools' passed here are instances.

        async with self._lock:
            for tool in tools:
                if tool.name in self.tools_map:
                    continue

                self.tools_map[tool.name] = tool

                # Create semantic signature (Phase 18: Added atomic file tools)
                signature = f"Tool: {tool.name}\nDescription: {tool.description}"
                if tool.name == "manage_file":
                    signature += "\nKeywords: read write create delete move copy mkdir list file folder directory filesystem update edit"
                elif tool.name == "read_file":
                    signature += "\nKeywords: read view file content text open"
                elif tool.name == "write_file":
                    signature += "\nKeywords: write create save file new content"
                elif tool.name == "edit_file":
                    signature += "\nKeywords: edit modify update replace change code refactor"
                elif tool.name == "list_files":
                    signature += "\nKeywords: list tree directory folder structure explore browse"
                elif tool.name == "file_system":
                    signature += "\nKeywords: mkdir delete remove move rename filesystem operations"
                elif tool.name == "explore_codebase":
                    signature += "\nKeywords: search find grep definition reference usage call graph navigation symbol class function"
                elif tool.name == "run_command":
                    signature += "\nKeywords: shell terminal bash execute test run script system cmd"
                elif tool.name == "manage_memory":
                    signature += "\nKeywords: memory remember preference config setting concept knowledge learn"

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
