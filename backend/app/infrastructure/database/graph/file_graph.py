"""
File-based Graph Storage for Embedded Mode.

Replaces Neo4j with a JSON file + networkx in-memory graph.
Suitable for small-to-medium projects.
"""

import json
import logging
import math
import threading
from pathlib import Path
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings

logger = logging.getLogger(__name__)


class FileGraphDriver:
    """
    File-based graph driver using networkx.
    Stores graph data as JSON and loads it into memory on startup.

    支持项目级隔离：
    - 传入 project_path: 存储到 {project}/.evoloop/code_graph.json
    - project_path=None: 使用全局路径（Atlas 等非项目数据）

    Thread-safety:
        Multiple FileGraphDriver instances may point to the same graph file
        (e.g. different Huey worker threads each have their own instance for the
        same project). A class-level lock keyed by the graph file path serializes
        all graph mutations and saves for a given file.
    """

    # Maps graph_file path -> threading.Lock shared by all driver instances
    # that target the same file.
    _file_locks: dict[Path, threading.Lock] = {}

    def __init__(self, project_path: str = None, data_dir: str = None):
        """
        初始化 FileGraphDriver。

        Args:
            project_path: 项目本地路径（如 /Users/xujin/Projects/evoloop）。
                         提供时，graph 存储在 {project}/.evoloop/code_graph.json
            data_dir: [已废弃] 向后兼容参数，优先使用 project_path
        """
        if project_path:
            from app.core.project.utils import get_graph_path
            self.graph_file = get_graph_path(project_path)
            self.project_path = project_path
        else:
            # 全局 fallback（Atlas 等非项目数据）
            self.data_dir = Path(data_dir or settings.SQLITE_PATH).parent
            self.graph_file = self.data_dir / "code_graph.json"
            self.project_path = None

        self._graph = None
        # All driver instances writing to the same file share one lock.
        with threading.Lock():
            if self.graph_file not in FileGraphDriver._file_locks:
                FileGraphDriver._file_locks[self.graph_file] = threading.Lock()
        self._lock = FileGraphDriver._file_locks[self.graph_file]
        self._load_graph()

    def _load_graph(self):
        """Load graph from JSON file or create new."""
        try:
            import networkx as nx
            if self.graph_file.exists():
                with open(self.graph_file, encoding='utf-8') as f:
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
        """
        Save graph to JSON file.

        Must be called while holding ``self._lock``.
        """
        if self._graph is None:
            return
        try:
            import networkx as nx
            data = nx.node_link_data(self._graph)
            # 确保目录存在
            self.graph_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.graph_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[FileGraph] Saved graph to {self.graph_file}")
        except Exception as e:
            logger.error(f"[FileGraph] Failed to save graph: {e}")

    def session(self):
        """Return a session context manager."""
        return FileGraphSession(self)

    async def execute_query(self, query: str, parameters: dict | None = None, **kwargs):
        """
        Execute Cypher-like query (limited support for Atlas and Retrieval).
        """
        if self._graph is None:
            return []

        params = parameters or {}
        # Merge kwargs into params (for calls like execute_query(q, bundle_id=...))
        params.update(kwargs)

        query_upper = query.upper()

        # 1. Atlas Transitions Pattern: MATCH (a:App)-[:HAS_STATE]->(s1)-[r:TRANSITION]->(s2)
        if "TRANSITION" in query_upper and "APP" in query_upper:
            bundle_id = params.get("bundle_id")
            platform = params.get("platform", "macos")

            results = []
            # Find App node
            apps = await self.find_nodes("App", {"bundle_id": bundle_id, "platform": platform})
            if not apps:
                return []

            # Since find_nodes returns attributes, we need the internal ID for traversal
            app_id = f"App:{bundle_id}"
            if app_id not in self._graph:
                return []

            # Traverse: App -> HAS_STATE -> State
            for s1_id in self._graph.successors(app_id):
                s1_attrs = self._graph.nodes[s1_id]
                if s1_attrs.get("_label") != "State":
                    continue

                # Traverse: State -> TRANSITION -> State
                for s2_id in self._graph.successors(s1_id):
                    edge_data = self._graph.get_edge_data(s1_id, s2_id)
                    if edge_data and edge_data.get("type") == "TRANSITION":
                        s2_attrs = self._graph.nodes[s2_id]
                        results.append({
                            "from_state": s1_attrs.get("state_id"),
                            "label": edge_data.get("action_label"),
                            "type": edge_data.get("action_type"),
                            "to_state": s2_attrs.get("state_id")
                        })
            return results

        # 2. Deletion Pattern: MATCH (f:File)-[:CONTAINS]->(e) DETACH DELETE e, f
        if "DETACH DELETE" in query_upper and "FILE" in query_upper:
            path = params.get("path")
            raw_pid = params.get("pid")
            pid = raw_pid if raw_pid is not None else params.get("project_id")

            # Use internal ID pattern
            file_id = f"File:{path}"
            if file_id in self._graph:
                # Find entities (CONTAINS)
                to_delete = [file_id]
                for n_id in list(self._graph.successors(file_id)):
                    edge_data = self._graph.get_edge_data(file_id, n_id)
                    if edge_data and edge_data.get("type") == "CONTAINS":
                        to_delete.append(n_id)

                # Remove nodes under lock so concurrent writers cannot corrupt
                # the graph file.
                with self._lock:
                    self._graph.remove_nodes_from(to_delete)
                    self._save_graph()
                return len(to_delete)
            return 0

        # 3. Aggregation Pattern: MATCH (c)-[:LINKED_TO]->(e:Memory) RETURN c.title, count(e)
        if "COUNT(" in query_upper and "LINKED_TO" in query_upper:
            counts = {}
            for _n_id, a in self._graph.nodes(data=True):
                if a.get("type") == "concept":
                    title = a.get("title") or a.get("name")
                    # Count outgoing LINKED_TO to Memory
                    links = [v_id for v_id in self._graph.successors(n_id)
                             if self._graph.get_edge_data(n_id, v_id).get("type") == "LINKED_TO"]
                    counts[title] = len(links)
            return [{"name": k, "count": v} for k, v in counts.items()]

        # 4. Cleanup Pattern: MATCH (n:LABEL) DETACH DELETE n
        # Also supports MATCH (n:LABEL {prop: $val}) and MATCH (n {prop: $val})
        if "DETACH DELETE N" in query_upper:
            import re

            # Try MATCH (n:LABEL) or MATCH (n:LABEL {prop: $val})
            match = re.search(r"MATCH\s*\(\s*(\w+)\s*:\s*(\w+)", query_upper)
            if match:
                label = match.group(2).capitalize()
                if label == "Codeentity":
                    label = "CodeEntity"
                # Extract inline filters {prop: $val} from original query to preserve param case
                filters = self._extract_inline_filters(query, params)
                return await self.delete_nodes(label, filters=filters or None)

            # Try MATCH (n {prop: $val}) without label
            match_no_label = re.search(r"MATCH\s*\(\s*\w+\s*\{\s*([^}]+)\s*\}\s*\)", query_upper)
            if match_no_label:
                filters = self._extract_inline_filters(query, params)
                with self._lock:
                    to_delete = []
                    for node_id, attrs in self._graph.nodes(data=True):
                        if all(attrs.get(k) == v for k, v in filters.items()):
                            to_delete.append(node_id)
                    if to_delete:
                        self._graph.remove_nodes_from(to_delete)
                        self._save_graph()
                return [{"deleted_count": len(to_delete)}]

        # 5. Ghost Node Cleanup Pattern: MATCH (n:CodeEntity) WHERE NOT (n)<-[:CONTAINS]-(:File)
        if "CODEENTITY" in query_upper and "WHERE NOT" in query_upper and "CONTAINS" in query_upper:
            pid = params.get("pid")
            with self._lock:
                to_delete = []
                for n_id, a in self._graph.nodes(data=True):
                    if a.get("_label") == "CodeEntity" and a.get("project_id") == pid:
                        # Check incoming CONTAINS from File
                        has_file = any(self._graph.nodes[u_id].get("_label") == "File"
                                     for u_id, v_id, d in self._graph.in_edges(n_id, data=True)
                                     if d.get("type") == "CONTAINS")
                        # Check incoming REFERENCES from Concept
                        has_concept = any(self._graph.nodes[u_id].get("_label") == "Concept"
                                        for u_id, v_id, d in self._graph.in_edges(n_id, data=True)
                                        if d.get("type") == "REFERENCES")

                        if not has_file and not has_concept:
                            to_delete.append(n_id)

                if to_delete:
                    self._graph.remove_nodes_from(to_delete)
                    self._save_graph()
            return [{"deleted_count": len(to_delete)}]

        # 6. Concept Retrieval Pattern: MATCH (c:Concept) RETURN c.name, c.description, c.id
        if "CONCEPT" in query_upper and "RETURN" in query_upper and "DETACH" not in query_upper:
            results = []
            for _n_id, a in self._graph.nodes(data=True):
                if a.get("_label") == "Concept" or a.get("type") == "concept":
                    results.append({
                        "name": a.get("name") or a.get("title"),
                        "desc": a.get("description") or a.get("content"),
                        "id": a.get("id")
                    })
            return results

        # 7. Basic Retrieval Fallback (CodeEntity search)
        if "CODEENTITY" in query_upper:
            name = params.get("name")
            raw_pid = params.get("pid")
            pid = raw_pid if raw_pid is not None else params.get("project_id")
            nodes = await self.find_nodes("CodeEntity", {"name": name, "project_id": pid})
            return nodes

        # 8. Memory Concept Aggregation: MATCH (c)-[:LINKED_TO]->(e:Memory) ... RETURN c.title as name, count(e) as count
        if "LINKED_TO" in query_upper and "COUNT(E)" in query_upper and "CONCEPT" in query_upper:
            counts = {} # title -> count
            for u, _v, d in self._graph.edges(data=True):
                if d.get("type") == "LINKED_TO":
                    src = self._graph.nodes[u]
                    # Check if source is a concept
                    if (src.get("_label") in ["Memory", "Concept"]) and src.get("type") == "concept":
                        title = src.get("title") or src.get("name")
                        if title:
                            counts[title] = counts.get(title, 0) + 1
            return [{"name": k, "count": v} for k, v in counts.items()]

        # 6. Concept Retrieval (for migration): MATCH (c:Concept)
        if "MATCH (C:CONCEPT)" in query_upper:
            nodes = await self.find_nodes("Concept")
            return [{
                "name": n.get("name") or n.get("title"),
                "desc": n.get("desc") or n.get("description"),
                "id": n.get("id")
            } for n in nodes]

        # 7. Index/Constraint/Maintenance (Silent handling)
        MAINTENANCE_KEYWORDS = ["DROP INDEX", "CREATE INDEX", "DROP CONSTRAINT", "CREATE CONSTRAINT", "CALL DB.INDEX"]
        if any(kw in query_upper for kw in MAINTENANCE_KEYWORDS):
            logger.info(f"[FileGraph] Maintenance query handled silently: {query[:50]}...")
            return []

        raise NotImplementedError(
            f"FileGraphDriver does not support this Cypher query pattern. "
            f"Query: {query[:100]}..."
        )

    @staticmethod
    def _extract_inline_filters(query: str, params: dict) -> dict:
        """Extract {key: $param} or {key: value} from a Cypher MATCH clause."""
        import re
        filters = {}
        match = re.search(r"\{\s*([^}]+)\s*\}", query)
        if match:
            for part in match.group(1).split(","):
                part = part.strip()
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                k = k.strip()
                v = v.strip()
                if v.startswith("$"):
                    filters[k] = params.get(v[1:])
                else:
                    # Strip quotes from literal values
                    filters[k] = v.strip("'\"")
        return filters

    async def verify_connectivity(self):
        """Verify graph is loaded."""
        return self._graph is not None

    async def close(self):
        """Save graph before closing."""
        with self._lock:
            self._save_graph()

    # --- High Level Agnostic API Implementation ---

    async def upsert_node(self, label: str, id_field: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Create or update a node in networkx."""
        if self._graph is None:
            return {}

        node_id = properties.get(id_field)
        if not node_id:
            raise ValueError(f"Property '{id_field}' missing for upsert into {label}")

        # In FileGraph, we use a global node ID (can be the same as id_field or prefixed)
        # To avoid collisions between different labels with same ID, we prefix it.
        internal_id = f"{label}:{node_id}"

        with self._lock:
            attrs = {**properties, "_label": label}
            if internal_id not in self._graph:
                self._graph.add_node(internal_id, **attrs)
            else:
                self._graph.nodes[internal_id].update(attrs)

            # [NEW] Sync Concept embeddings to unified vector store for better performance/standardization
            if label == "Concept" and "embedding" in properties:
                try:
                    from app.infrastructure.database.vector import get_vector_store
                    vector_store = get_vector_store()
                    vector_store.upsert_concept_chunks([{
                        "id": node_id,
                        "name": properties.get("name") or properties.get("title", ""),
                        "description": properties.get("description") or properties.get("content", ""),
                        "project_id": properties.get("project_id", DEFAULT_PROJECT_ID),
                        "vector": properties["embedding"]
                    }])
                except Exception as ve:
                    logger.warning(f"[FileGraph] Failed to sync Concept vector to store: {ve}")

            self._save_graph()
            return dict(self._graph.nodes[internal_id])

    async def find_nodes(self, label: str, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Find nodes matching filters using networkx."""
        if self._graph is None:
            return []

        results = []
        for _, attrs in self._graph.nodes(data=True):
            if attrs.get("_label") != label:
                continue

            match = True
            if filters:
                for k, v in filters.items():
                    if attrs.get(k) != v:
                        match = False
                        break

            if match:
                results.append(attrs)
                if len(results) >= limit:
                    break
        return results

    async def delete_nodes(self, label: str, filters: dict[str, Any] | None = None, detach: bool = True) -> int:
        """Delete nodes matching filters."""
        if self._graph is None:
            return 0

        with self._lock:
            to_delete = []
            for node_id, attrs in self._graph.nodes(data=True):
                if attrs.get("_label") != label:
                    continue

                match = True
                if filters:
                    for k, v in filters.items():
                        if attrs.get(k) != v:
                            match = False
                            break
                if match:
                    to_delete.append(node_id)

            count = len(to_delete)
            if count > 0:
                self._graph.remove_nodes_from(to_delete)
                self._save_graph()
            return count

    async def link_nodes(
        self,
        src_label: str,
        src_filters: dict,
        tgt_label: str,
        tgt_filters: dict,
        rel_type: str,
        rel_props: dict[str, Any] | None = None,
    ) -> bool:
        """Create a relationship between nodes in networkx."""
        if self._graph is None:
            return False

        with self._lock:
            src_nodes = [nid for nid, attrs in self._graph.nodes(data=True)
                         if attrs.get("_label") == src_label and all(attrs.get(k) == v for k, v in src_filters.items())]
            tgt_nodes = [nid for nid, attrs in self._graph.nodes(data=True)
                         if attrs.get("_label") == tgt_label and all(attrs.get(k) == v for k, v in tgt_filters.items())]

            if not src_nodes or not tgt_nodes:
                return False

            linked = False
            edge_attrs = {**(rel_props or {}), "type": rel_type}
            for s in src_nodes:
                for t in tgt_nodes:
                    self._graph.add_edge(s, t, **edge_attrs)
                    linked = True

            if linked:
                self._save_graph()
            return linked

    async def traverse(
        self,
        start_label: str,
        start_filters: dict,
        rel_type: str,
        target_label: str | None = None,
        direction: str = "out",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Traverse the networkx graph."""
        if self._graph is None:
            return []

        start_nodes = [nid for nid, attrs in self._graph.nodes(data=True)
                       if attrs.get("_label") == start_label and all(attrs.get(k) == v for k, v in start_filters.items())]

        results = []
        seen = set()

        for s in start_nodes:
            if direction == "out":
                neighbors = self._graph.successors(s)
            else:
                neighbors = self._graph.predecessors(s)

            for n in neighbors:
                if n in seen:
                    continue

                # Check edge type
                edge_data = self._graph.get_edge_data(s, n) if direction == "out" else self._graph.get_edge_data(n, s)
                if edge_data and edge_data.get("type") == rel_type:
                    attrs = self._graph.nodes[n]
                    if target_label and attrs.get("_label") != target_label:
                        continue

                    results.append(attrs)
                    seen.add(n)
                    if len(results) >= limit:
                        return results
        return results

    async def search_similar(
        self,
        label: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform a vector similarity search on nodes (delegates to VectorStore for Concepts)."""
        if self._graph is None:
            return []

        if label == "Concept":
            from app.infrastructure.database.vector import get_vector_store
            vector_store = get_vector_store()

            # 1. Search in unified vector store
            vec_results = vector_store.search_concepts(query_embedding, top_k=top_k)
            if not vec_results:
                return []

            # 2. Re-hydrate from FileGraph
            results = []
            for r in vec_results:
                internal_id = f"Concept:{r['id']}"
                if internal_id in self._graph:
                    results.append(self._graph.nodes[internal_id])
            return results

        # Fallback for other labels: Manual cosine similarity on in-memory graph
        candidates = []
        for _n_id, attrs in self._graph.nodes(data=True):
            if attrs.get("_label") != label:
                continue

            # Apply filters
            if filters:
                match = True
                for k, v in filters.items():
                    if attrs.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            # Check for embedding
            embedding = attrs.get("embedding")
            if not embedding or not isinstance(embedding, list):
                continue

            # Calculate similarity
            sim = self._cosine_similarity(query_embedding, embedding)
            candidates.append((sim, attrs))

        # Sort by similarity descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:top_k]]

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Helper for cosine similarity."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2, strict=False))
        mag1 = math.sqrt(sum(a * a for a in v1))
        mag2 = math.sqrt(sum(a * a for a in v2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot_product / (mag1 * mag2)


class FileGraphSession:
    """Session for file-based graph operations."""

    def __init__(self, driver: FileGraphDriver):
        self.driver = driver
        self._modified = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._modified:
            with self.driver._lock:
                self.driver._save_graph()

    async def run(self, query: str, parameters: dict | None = None, **kwargs):
        """
        Legacy Cypher-like query handler.

        Dispatches to the driver's unified execute_query pattern matcher.
        """
        results = await self.driver.execute_query(query, parameters=parameters, **kwargs)
        # Some maintenance queries might modify the graph via find_nodes/delete_nodes/upsert_node
        # but execute_query itself is typically read-only or handled silently.
        return FileGraphResult(results)

    async def _handle_merge(self, query: str, parameters: dict):
        """Handle MERGE (create/update) operations."""

        # Extract node info from MERGE (n:Label {prop: $val})
        # Simplified parsing - assumes single node merge
        node_id = parameters.get('path') or parameters.get('name') or str(hash(str(parameters)))

        with self.driver._lock:
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
        raw_pid = parameters.get('pid')
        pid = raw_pid if raw_pid is not None else parameters.get('project_id')
        path = parameters.get('path')

        matched_nodes = []

        for node_id, attrs in G.nodes(data=True):
            match = True
            if name and attrs.get('name') != name:
                match = False
            if pid is not None and attrs.get('project_id') != pid:
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
            with self.driver._lock:
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
