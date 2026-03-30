"""
Unified Graph Service
=====================

Merged functionality from:
- GraphExplorer (natural language queries)
- GraphRetrievalService (structured queries)

Provides a single interface for all Neo4j graph operations.
"""

import logging
from typing import Any

from langchain_core.prompts.prompt import PromptTemplate

from app.core.config import settings
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.llm.factory import LLMFactory, get_default_llm

logger = logging.getLogger(__name__)


class GraphService:
    """
    Unified service for Neo4j graph operations.
    
    Combines functionality from previous GraphExplorer and GraphRetrievalService
    to eliminate redundancy.
    """

    def __init__(self):
        # Skip initialization in Embedded Mode (no Neo4j)
        self._graph = None
        self._embedded_mode = settings.EMBEDDED_MODE
        
        if self._embedded_mode:
            logger.debug("GraphService: Disabled in Embedded Mode (Neo4j not available)")
            return

        # Initialize LangChain Neo4jGraph for NL queries
        try:
            from langchain_neo4j import Neo4jGraph
            
            self._graph = Neo4jGraph(
                url=settings.NEO4J_URI,
                username=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
                refresh_schema=False,
            )
            
            # Define schema explicitly (bypassing APOC)
            self._graph.schema = """
Node properties:
- **File**
  - path: STRING (The relative file path, e.g. 'app/main.py')
  - project_id: INTEGER
  - last_indexed: INTEGER
- **CodeEntity**
  - name: STRING (Short name, e.g. 'UserService')
  - full_name: STRING (Fully qualified name)
  - type: STRING (e.g. 'function', 'class', 'method')
  - project_id: INTEGER

Relationship properties:
- **RELATION**
  - type: STRING (e.g. 'calls', 'imports', 'inherits')

Relationships:
(:File)-[:CONTAINS]->(:CodeEntity)
(:CodeEntity)-[:RELATION]->(:CodeEntity)
"""
            logger.info("GraphService initialized with manual schema")
            
        except Exception as e:
            logger.error(f"Failed to initialize Neo4jGraph: {e}")
            self._graph = None

    # =================================================================================
    # Structured Queries (from former GraphRetrievalService)
    # =================================================================================

    async def find_symbol_definition(self, symbol_name: str, project_id: int) -> list[dict[str, Any]]:
        """Find a symbol definition using Graph."""
        driver = await get_graph_db()
        query = """
        MATCH (e:CodeEntity {name: $name, project_id: $pid})
        MATCH (f:File)-[:CONTAINS]->(e)
        RETURN e.full_name as full_name, e.type as type, f.path as file_path, e.score as score
        LIMIT 10
        """
        async with driver.session() as session:
            result = await session.run(query, name=symbol_name, pid=project_id)
            return await result.data()

    async def find_usages(self, symbol_name: str, project_id: int) -> list[dict[str, Any]]:
        """Find who uses (calls/references) this symbol."""
        driver = await get_graph_db()
        query = """
        MATCH (target:CodeEntity {name: $name, project_id: $pid})
        MATCH (source:CodeEntity)-[r]->(target)
        MATCH (f:File)-[:CONTAINS]->(source)
        RETURN source.full_name as source, r.type as relation, f.path as file_path, target.full_name as target
        LIMIT 50
        """
        async with driver.session() as session:
            result = await session.run(query, name=symbol_name, pid=project_id)
            return await result.data()

    async def get_call_hierarchy(self, symbol_name: str, project_id: int, depth: int = 2) -> dict[str, Any]:
        """Get recursive call hierarchy (Who calls me, who do I call)."""
        driver = await get_graph_db()

        incoming_query = f"""
        MATCH (target:CodeEntity {{name: $name, project_id: $pid}})
        MATCH path = (source)-[:RELATION*1..{depth}]->(target)
        RETURN path
        LIMIT 20
        """

        outgoing_query = f"""
        MATCH (source:CodeEntity {{name: $name, project_id: $pid}})
        MATCH path = (source)-[:RELATION*1..{depth}]->(target)
        RETURN path
        LIMIT 20
        """

        async with driver.session() as session:
            in_res = await session.run(incoming_query, name=symbol_name, pid=project_id)
            in_paths = await in_res.data()

            out_res = await session.run(outgoing_query, name=symbol_name, pid=project_id)
            out_paths = await out_res.data()

            return {
                "incoming": len(in_paths),
                "outgoing": len(out_paths),
                "details": "Graph paths fetched (summarized for now)",
            }

    # =================================================================================
    # Natural Language Queries (from former GraphExplorer)
    # =================================================================================

    async def natural_language_query(self, question: str, project_id: int | None = None) -> str:
        """
        Ask a natural language question about the graph.
        
        Args:
            question: User's question (e.g. "Who calls function process_payment?")
            project_id: Optional context to restrict search
        """
        if not self._graph:
            return "Graph Service is not available (Neo4j not connected or in Embedded Mode)."

        from langchain_neo4j import GraphCypherQAChain

        llm = get_default_llm(temperature=0)

        from app.utils import render_template
        prompt_text = render_template(
            "tool/cypher_generation.prompt.j2",
            schema="{schema}", # Keep LangChain placeholders {schema} and {question} or pass data directly?
            question="{question}",
            project_id=project_id if project_id and project_id != 0 else None
        )

        CYPHER_GENERATION_PROMPT = PromptTemplate(
            input_variables=["schema", "question"],
            template=prompt_text
        )

        chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self._graph,
            verbose=True,
            cypher_prompt=CYPHER_GENERATION_PROMPT,
            allow_dangerous_requests=True,
        )

        try:
            result = await chain.ainvoke({"query": question})
            return result["result"]
        except Exception as e:
            logger.error(f"Graph NL Query Failed: {e}")
            return f"I couldn't query the graph: {e}"

    async def query_cypher(self, cypher_query: str, params: dict | None = None) -> list[dict]:
        """
        Execute raw Cypher query directly.
        
        Args:
            cypher_query: Raw Cypher query string
            params: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        driver = await get_graph_db()
        async with driver.session() as session:
            result = await session.run(cypher_query, params or {})
            return await result.data()


# Global Instance
graph_service = GraphService()

# Backward compatibility aliases
# TODO: Migrate callers to use graph_service directly
graph_retrieval_service = graph_service
graph_explorer = graph_service
