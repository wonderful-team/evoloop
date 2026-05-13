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
from app.infrastructure.database.graph.driver import GraphManager, get_graph_db
from app.infrastructure.llm.factory import get_default_llm

logger = logging.getLogger(__name__)


class GraphService:
    """
    Unified service for Neo4j graph operations.
    
    Combines functionality from previous GraphExplorer and GraphRetrievalService
    to eliminate redundancy.
    """

    def __init__(self):
        # Always initialize driver through GraphManager
        self._driver = GraphManager.get_driver()
        self._graph = None # For QAChain (Neo4j only)
        self._embedded_mode = settings.EMBEDDED_MODE
        
        if self._embedded_mode:
            logger.info("GraphService: Running in Embedded Mode (FileGraph)")
        else:
            logger.info("GraphService: Running in Neo4j Mode")

        # Initialize LangChain Neo4jGraph for NL queries (Production Mode only)
        if not self._embedded_mode:
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
        """Find a symbol definition using high-level API."""
        # MATCH (e:CodeEntity {name: $name, project_id: $pid})
        # MATCH (f:File)-[:CONTAINS]->(e)
        entities = await self._driver.find_nodes("CodeEntity", {"name": symbol_name, "project_id": project_id})
        
        results = []
        for e in entities:
            # Reverse traverse: Entity -> File (who CONTAINS me)
            files = await self._driver.traverse(
                "CodeEntity", {"full_name": e["full_name"]},
                rel_type="CONTAINS",
                direction="in",
                target_label="File"
            )
            file_path = files[0]["path"] if files else "unknown"
            results.append({
                "full_name": e["full_name"],
                "type": e.get("type"),
                "file_path": file_path,
                "score": e.get("score")
            })
        return results

    async def find_usages(self, symbol_name: str, project_id: int) -> list[dict[str, Any]]:
        """Find who uses (calls/references) this symbol."""
        # Find the target entity first
        targets = await self._driver.find_nodes("CodeEntity", {"name": symbol_name, "project_id": project_id})
        
        results = []
        for target in targets:
            # Traverse any relationship incoming to this target
            # Note: rel_type="RELATION" is used for generic links
            sources = await self._driver.traverse(
                "CodeEntity", {"full_name": target["full_name"]},
                rel_type="RELATION",
                direction="in",
                target_label="CodeEntity"
            )
            
            for src in sources:
                # Find file for source
                files = await self._driver.traverse(
                    "CodeEntity", {"full_name": src["full_name"]},
                    rel_type="CONTAINS",
                    direction="in",
                    target_label="File"
                )
                results.append({
                    "source": src["full_name"],
                    "relation": "references", # Simplified
                    "file_path": files[0]["path"] if files else "unknown",
                    "target": target["full_name"]
                })
        return results

    async def get_call_hierarchy(self, symbol_name: str, project_id: int, depth: int = 2) -> dict[str, Any]:
        """Get recursive call hierarchy (Who calls me, who do I call) using high-level API."""
        # Find starting nodes
        nodes = await self._driver.find_nodes("CodeEntity", {"name": symbol_name, "project_id": project_id})
        if not nodes:
            return {"incoming": 0, "outgoing": 0, "details": "Symbol not found"}

        incoming_total = 0
        outgoing_total = 0
        
        for node in nodes:
            full_name = node["full_name"]
            
            # Incoming (Who calls me)
            in_nodes = await self._driver.traverse(
                "CodeEntity", {"full_name": full_name},
                rel_type="RELATION",
                direction="in",
                target_label="CodeEntity",
                limit=20
            )
            incoming_total += len(in_nodes)
            
            # Outgoing (Who do I call)
            out_nodes = await self._driver.traverse(
                "CodeEntity", {"full_name": full_name},
                rel_type="RELATION",
                direction="out",
                target_label="CodeEntity",
                limit=20
            )
            outgoing_total += len(out_nodes)

        return {
            "incoming": incoming_total,
            "outgoing": outgoing_total,
            "details": f"Analyzed {len(nodes)} entities for {symbol_name}",
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

        llm = await get_default_llm(temperature=0)

        from app.utils import render_template
        prompt_text = render_template(
            "domain/codebase/cypher_generation.prompt.j2",
            schema="{schema}", # Keep LangChain placeholders {schema} and {question} or pass data directly?
            question="{question}",
            project_id=project_id if project_id and project_id != 0 else None
        )

        cypher_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=prompt_text
        )

        chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self._graph,
            verbose=True,
            cypher_prompt=cypher_prompt,
            allow_dangerous_requests=True,
        )

        try:
            result = await chain.ainvoke({"query": question})
            return result["result"]
        except Exception as e:
            logger.error(f"Graph NL Query Failed: {e}")
            return f"I couldn't query the graph: {e}"

    async def query_cypher(self, cypher_query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Execute raw Cypher query directly using the driver.
        """
        return await self._driver.execute_query(cypher_query, parameters=params)

    async def multi_entity_query(
        self,
        entities: list[str],
        operator: str,
        question: str | None = None,
        project_id: int | None = None,
    ) -> str:
        """
        Query relationships involving multiple entities using high-level API.
        """
        # If Neo4j is available, we can still use Cypher for performance if preferred,
        # but for full unification, we'll implement a driver-agnostic logic here.
        # Actually, let's keep it simple: Find who relates to ANY or ALL targets.
        
        results = []
        
        # 1. Find all target nodes
        all_targets = []
        for name in entities:
            nodes = await self._driver.find_nodes("CodeEntity", {"name": name, "project_id": project_id})
            all_targets.extend(nodes)
            
        if not all_targets:
            return f"No entities found for: {', '.join(entities)}"

        # 2. For each target, find its incoming relations
        caller_map = {} # full_name -> {type, matched_targets: set}
        
        for target in all_targets:
            sources = await self._driver.traverse(
                "CodeEntity", {"full_name": target["full_name"]},
                rel_type="RELATION",
                direction="in",
                target_label="CodeEntity"
            )
            
            for src in sources:
                s_name = src["full_name"]
                if s_name not in caller_map:
                    caller_map[s_name] = {"type": src.get("type", "unknown"), "matched_targets": set()}
                caller_map[s_name]["matched_targets"].add(target["name"])

        # 3. Filter based on operator
        filtered_callers = []
        if operator == "and":
            target_set = set(entities)
            for s_name, data in caller_map.items():
                if target_set.issubset(data["matched_targets"]):
                    filtered_callers.append((s_name, data))
        else:
            for s_name, data in caller_map.items():
                filtered_callers.append((s_name, data))

        if not filtered_callers:
            return f"No shared relationships found for entities: {', '.join(entities)}"

        # 4. Format Output
        lines = [f"Graph Query Results for entities: {', '.join(entities)}",
                 f"Operator: {operator.upper()} (project_id: {project_id})",
                 ""]
        
        lines.append(f"Found {len(filtered_callers)} entities that match the criteria:")
        for name, data in filtered_callers[:50]:
            lines.append(f"  • {name} ({data['type']})")
            lines.append(f"    Relates to: {', '.join(data['matched_targets'])}")
            
        if len(filtered_callers) > 50:
            lines.append(f"\n... and {len(filtered_callers) - 50} more")
            
        return "\n".join(lines)


# Global Instance
graph_service = GraphService()
