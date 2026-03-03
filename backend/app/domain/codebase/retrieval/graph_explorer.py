import logging

from langchain_core.prompts.prompt import PromptTemplate
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph

from app.core.config import settings
from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


class GraphExplorer:
    """
    Exploratory Graph Retrieval using LangChain's Text-to-Cypher capabilities.
    """

    def __init__(self):
        # We need a synchronous Neo4j connection for LangChain.
        # PROBLEM: Default Neo4jGraph requires APOC plugin for schema retrieval.
        # FIX: We manually define the schema to avoid APOC dependency.

        try:
            self.graph = Neo4jGraph(
                url=settings.NEO4J_URI,
                username=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
                refresh_schema=False,  # Prevent auto-APOC call in constructor if supported (v0.1.0+ likely supports)
            )

            # If refresh_schema=False didn't exist or didn't work as expected in older versions,
            # we might need to manually set the schema string.
            # Defining the schema explicitly:
            self.graph.schema = """
Node properties:
- **File**
  - path: STRING (The relative file path, e.g. 'app/main.py'. Use this as the filename.)
  - project_id: INTEGER
  - last_indexed: INTEGER
- **CodeEntity**
  - name: STRING (Short name, e.g. 'UserService')
  - full_name: STRING (Fully qualified name, e.g. 'app.services.UserService')
  - type: STRING (e.g. 'function', 'class', 'method')
  - project_id: INTEGER

Relationship properties:
- **RELATION**
  - type: STRING (e.g. 'calls', 'imports', 'inherits', 'instantiates')

The relationships:
(:File)-[:CONTAINS]->(:CodeEntity)
(:CodeEntity)-[:RELATION]->(:CodeEntity)
"""
            # Also set structured schema if needed by newer langchain versions
            # self.graph.structured_schema = ...

            logger.info("GraphExplorer initialized with manual schema (bypassing APOC).")

        except TypeError:
            # Fallback if refresh_schema param doesn't exist in installed version
            try:
                self.graph = Neo4jGraph(
                    url=settings.NEO4J_URI,
                    username=settings.NEO4J_USER,
                    password=settings.NEO4J_PASSWORD,
                )
                # It likely failed inside init, but let's try our best or log.
            except Exception as e:
                logger.error(f"Failed to initialize Neo4jGraph (Standard): {e}")
                # Last resort: Mock object? Or just accept failure.
                self.graph = None

        except Exception as e:
            logger.error(f"Failed to initialize Neo4jGraph for LangChain: {e}")
            self.graph = None

    async def query(self, question: str, project_id: int | None = None) -> str:
        """
        Ask a natural language question about the graph.
        Args:
            question: User's question (e.g. "Who calls function process_payment?")
            project_id: Optional context to restrict search (not strictly enforced by Chain unless prompted)
        """
        if not self.graph:
            return "Graph Explorer is not available (Connection failed)."

        llm = LLMFactory.create_llm(temperature=0)  # Low temp for code generation

        # Custom Prompt to inject schema hints or project context
        CYPHER_GENERATION_TEMPLATE = """Task:Generate Cypher statement to query a graph database.
Instructions:
Use only the provided relationship types and properties in the schema.
Do not use any other relationship types or properties that are not provided.
Schema:
{schema}

Note: Do not include any explanations or apologies in your responses.
Do not respond to any questions that might ask anything else than for you to construct a Cypher statement.
Do not include any text except the generated Cypher statement.

The question is:
{question}
"""
        # Note: project_id can be 0 (global mode), skip constraint in that case
        if project_id is not None and project_id != 0:
            CYPHER_GENERATION_TEMPLATE += f"\nConstraint: ALWAYS filter by project_id = {project_id} in your query if nodes have that property."

        CYPHER_GENERATION_PROMPT = PromptTemplate(
            input_variables=["schema", "question"],
            template=CYPHER_GENERATION_TEMPLATE
        )

        chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.graph,
            verbose=True,
            cypher_prompt=CYPHER_GENERATION_PROMPT,
            allow_dangerous_requests=True,
        )

        try:
            # invoke/ainvoke
            result = await chain.ainvoke({"query": question})
            return result["result"]
        except Exception as e:
            logger.error(f"Graph Explorer Query Failed: {e}")
            return f"I couldn't query the graph: {e}"


# Global instance
graph_explorer = GraphExplorer()
