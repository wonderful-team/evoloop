"""
File-based Graph Storage for Embedded Mode.

Replaces Neo4j with a JSON file + networkx in-memory graph.
Suitable for small-to-medium projects.
"""

import json
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class FileGraphDriver:
    """
    File-based graph driver using networkx.
    Stores graph data as JSON and loads it into memory on startup.
    """

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or settings.SQLITE_PATH).parent
        self.graph_file = self.data_dir / "code_graph.json"
        self._graph = None
        self._load_graph()

    def _load_graph(self):
        """Load graph from JSON file or create new."""
        try:
            import networkx as nx
            if self.graph_file.exists():
                with open(self.graph_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._graph = nx.node_link_graph(data)
                logger.info(f"[FileGraph] Loaded {self._graph.number_of_nodes()} nodes, "
                           f"{self._graph.number_of_edges()} edges from {self.graph_file}")
            else:
                self._graph = nx.DiGraph()
                logger.info("[FileGraph] Created new graph")
        except ImportError:
            logger.warning("[FileGraph] networkx not installed, graph features disabled")
            self._graph = None
        except Exception as e:
            logger.error(f"[FileGraph] Failed to load graph: {e}")
            self._graph = None

    def _save_graph(self):
        """Save graph to JSON file."""
        if self._graph is None:
            return
        try:
            import networkx as nx
            data = nx.node_link_data(self._graph)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.graph_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[FileGraph] Saved graph to {self.graph_file}")
        except Exception as e:
            logger.error(f"[FileGraph] Failed to save graph: {e}")

    def session(self):
        """Return a session context manager."""
        return FileGraphSession(self)

    async def execute_query(self, query: str, parameters: dict = None, **kwargs):
        """Execute Cypher-like query (limited support)."""
        # For now, return empty - use session-based API instead
        return []

    async def verify_connectivity(self):
        """Verify graph is loaded."""
        return self._graph is not None

    async def close(self):
        """Save graph before closing."""
        self._save_graph()


class FileGraphSession:
    """Session for file-based graph operations."""

    def __init__(self, driver: FileGraphDriver):
        self.driver = driver
        self._modified = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._modified:
            self.driver._save_graph()

    async def run(self, query: str, parameters: dict = None, **kwargs):
        """
        Run a Cypher-like query.

        Supported patterns:
        - MERGE (n:Label {prop: $val}) - Create/update node
        - MATCH (n)-[r]->(m) RETURN n, m - Find relationships
        - MATCH (n) DETACH DELETE n - Delete node
        """
        if self.driver._graph is None:
            return FileGraphResult([])

        parameters = parameters or {}
        # Merge kwargs into parameters (Neo4j-style positional params)
        if kwargs:
            parameters = {**parameters, **kwargs}
        query = query.strip()

        try:
            if query.upper().startswith("MERGE"):
                return await self._handle_merge(query, parameters)
            elif query.upper().startswith("MATCH"):
                return await self._handle_match(query, parameters)
            else:
                logger.warning(f"[FileGraph] Unsupported query: {query[:50]}")
                return FileGraphResult([])
        except Exception as e:
            logger.error(f"[FileGraph] Query error: {e}")
            return FileGraphResult([])

    async def _handle_merge(self, query: str, parameters: dict):
        """Handle MERGE (create/update) operations."""

        # Extract node info from MERGE (n:Label {prop: $val})
        # Simplified parsing - assumes single node merge
        node_id = parameters.get('path') or parameters.get('name') or str(hash(str(parameters)))

        if 'DETACH DELETE' in query.upper():
            # Handle delete
            if node_id in self.driver._graph:
                self.driver._graph.remove_node(node_id)
                self._modified = True
            return FileGraphResult([])

        # Create or update node
        if node_id not in self.driver._graph:
            self.driver._graph.add_node(node_id, **parameters)
        else:
            # Update existing node attributes
            self.driver._graph.nodes[node_id].update(parameters)

        self._modified = True
        return FileGraphResult([{"node": node_id}])

    async def _handle_match(self, query: str, parameters: dict):
        """Handle MATCH (query) operations."""
        G = self.driver._graph
        results = []

        # Detect delete operations
        is_delete = "DETACH DELETE" in query.upper()
        has_optional_delete = "OPTIONAL MATCH" in query and "DETACH DELETE" in query

        # Find by property
        name = parameters.get('name')
        pid = parameters.get('pid') or parameters.get('project_id')
        path = parameters.get('path')

        matched_nodes = []

        for node_id, attrs in G.nodes(data=True):
            match = True
            if name and attrs.get('name') != name:
                match = False
            if pid and attrs.get('project_id') != pid:
                match = False
            if path and attrs.get('path') != path:
                match = False

            if match:
                if is_delete:
                    matched_nodes.append(node_id)
                    # If OPTIONAL MATCH + DETACH DELETE, also remove successor nodes
                    # to simulate deleting related entities (e.g., File -> CONTAINS -> entities)
                    if has_optional_delete:
                        for succ in list(G.successors(node_id)):
                            if succ not in matched_nodes:
                                matched_nodes.append(succ)
                else:
                    results.append({
                        "full_name": attrs.get('full_name', node_id),
                        "type": attrs.get('type', 'unknown'),
                        "file_path": attrs.get('path', ''),
                        "score": attrs.get('score', 0),
                    })

        if is_delete:
            deleted_count = 0
            for node_id in matched_nodes:
                if node_id in G:
                    G.remove_node(node_id)
                    deleted_count += 1
            if deleted_count > 0:
                self._modified = True
            return FileGraphResult([{"deleted_count": deleted_count}])

        return FileGraphResult(results)


class FileGraphResult:
    """Result wrapper for file graph queries."""

    def __init__(self, data: list):
        self._data = data

    def __aiter__(self):
        return iter(self._data)

    async def data(self):
        return self._data

    async def single(self):
        return self._data[0] if self._data else None
