"""
LangChain Neo4j Graph Adapter
=============================

Encapsulates the langchain_neo4j dependency so that core/domain layers
do not directly import third-party Neo4j clients. All LangChain-specific
graph initialization lives in this infrastructure module.
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Reusable schema definition for Cypher generation
_MANUAL_SCHEMA = """
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


def create_langchain_graph() -> Any | None:
    """
    Create a LangChain Neo4jGraph instance for natural-language queries.

    Returns:
        Neo4jGraph instance in production mode, or None in embedded mode
        or when Neo4j is unreachable.
    """
    if settings.EMBEDDED_MODE:
        return None

    try:
        from langchain_neo4j import Neo4jGraph

        graph = Neo4jGraph(
            url=settings.NEO4J_URI,
            username=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
            refresh_schema=False,
        )
        graph.schema = _MANUAL_SCHEMA
        logger.info("[LangchainGraphAdapter] Neo4jGraph initialized with manual schema")
        return graph
    except Exception as e:
        logger.warning(f"[LangchainGraphAdapter] Failed to initialize Neo4jGraph (falling back): {e}")
        return None


def create_cypher_qa_chain(llm: Any, graph: Any, prompt: Any) -> Any:
    """
    Build a GraphCypherQAChain from a LangChain LLM and Neo4jGraph.

    This factory keeps the langchain_neo4j import inside the
    infrastructure layer. Raises in embedded mode as a defense-in-depth
    guard (callers should already check EMBEDDED_MODE before calling).
    """
    if settings.EMBEDDED_MODE:
        raise RuntimeError("Cypher QA chain is not available in embedded mode")

    from langchain_neo4j import GraphCypherQAChain

    return GraphCypherQAChain.from_llm(
        llm=llm,
        graph=graph,
        verbose=True,
        cypher_prompt=prompt,
        allow_dangerous_requests=True,
    )
