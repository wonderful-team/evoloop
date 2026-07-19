"""ModuleGraphService — project module graph infrastructure.

Builds a structured understanding of a codebase via Leiden community
detection on ``CodeRelation`` edges, then provides query methods that
all consumers (Wiki Agent, AppMap grouping, macro management, Overview,
incremental generation) use to understand project structure.

Usage::
    service = ModuleGraphService()
    modules = await service.get_modules(project_id=121)
    for m in modules:
        print(m.name, m.entities)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.infrastructure.database import session_scope

logger = logging.getLogger(__name__)

# ── cache ──────────────────────────────────────────────────────────
_cache: dict[int, tuple[float, ModuleGraph]] = {}
_CACHE_TTL = 86400  # 24 h


# ── data model ──────────────────────────────────────────────────────
@dataclass
class Module:
    name: str
    entities: list[str]
    entity_count: int
    summary: str


@dataclass
class ModuleGraph:
    modules: list[Module]
    entity_to_module: dict[str, str]  # entity_name → module.name
    adjacency: list[tuple[str, str]]  # (module_a, module_b) — cross-module call

    def impact_set(self, changed_entities: set[str]) -> set[str]:
        """Return the minimal set of modules that need regeneration.

        Starts with modules directly containing *changed_entities*, then
        BFS along cross-module adjacency edges (depth ≤ 2).
        """
        direct: set[str] = set()
        for e in changed_entities:
            m = self.entity_to_module.get(e)
            if m:
                direct.add(m)
        if not direct:
            return set()

        # BFS with depth limit
        graph: dict[str, list[str]] = defaultdict(list)
        for a, b in self.adjacency:
            graph[a].append(b)
            graph[b].append(a)

        result: set[str] = set(direct)
        queue: deque[tuple[str, int]] = deque((m, 0) for m in direct)
        while queue:
            node, depth = queue.popleft()
            if depth >= 2:
                continue
            for neighbor in graph.get(node, []):
                if neighbor not in result:
                    result.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return result

    def format_summary(self, include_graph: bool = False) -> str:
        """Human-readable summary, e.g. "商品管理(12) 订单管理(8) …"."""
        parts = [f"{m.name}({m.entity_count}实体)" for m in self.modules]
        s = "，".join(parts)
        if include_graph and self.adjacency:
            edges = " → ".join(f"{a}↔{b}" for a, b in self.adjacency[:5])
            s += f" | 模块间依赖: {edges}"
        return s


# ── service ─────────────────────────────────────────────────────────
class ModuleGraphService:
    """Build and query the project module graph."""

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    async def refresh(self, project_id: int) -> ModuleGraph:
        """Run Leiden clustering + LLM naming, cache result."""
        graph = await self._build(project_id)
        _cache[project_id] = (time.time(), graph)
        logger.info("[ModuleGraph] Refreshed for project %s (%d modules)", project_id, len(graph.modules))
        return graph

    async def get_modules(self, project_id: int) -> list[Module]:
        """Return cached modules (auto-refresh if stale/missing)."""
        g = await self._get_or_refresh(project_id)
        return g.modules

    async def get_module_of(self, project_id: int, entity: str) -> str | None:
        g = await self._get_or_refresh(project_id)
        return g.entity_to_module.get(entity)

    async def impact_set(self, project_id: int, changed_entities: set[str]) -> set[str]:
        g = await self._get_or_refresh(project_id)
        return g.impact_set(changed_entities)

    async def format_summary(self, project_id: int, include_graph: bool = False) -> str:
        g = await self._get_or_refresh(project_id)
        return g.format_summary(include_graph=include_graph)

    async def compute_impact(
        self,
        project_id: int,
        changed_entities: set[str],
    ) -> set[str]:
        """Return all entities that need regeneration, given a set of changed ones."""
        if not changed_entities:
            return set()
        affected_modules = await self.impact_set(project_id, changed_entities)
        if not affected_modules:
            return changed_entities
        # Expand modules back to entities
        all_modules = await self.get_modules(project_id)
        result: set[str] = set(changed_entities)
        for m in all_modules:
            if m.name in affected_modules:
                result.update(m.entities)
        return result

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------
    async def _get_or_refresh(self, project_id: int) -> ModuleGraph:
        cached = _cache.get(project_id)
        if cached and (time.time() - cached[0]) < _CACHE_TTL:
            return cached[1]
        return await self.refresh(project_id)

    async def _build(self, project_id: int) -> ModuleGraph:
        """Load CodeRelation edges → Leiden → LLM name clusters → ModuleGraph."""
        from app.domain.codebase.generation.leiden import run_leiden

        edges = await self._fetch_edges(project_id)
        if not edges:
            logger.info("[ModuleGraph] No CodeRelation for project %s", project_id)
            return self._empty_graph()

        communities = run_leiden(edges)
        if not communities:
            logger.info("[ModuleGraph] Leiden returned no communities for project %s", project_id)
            return self._empty_graph()

        named = await self._name_clusters(project_id, communities)
        self._log_gaps(communities, named)

        modules: list[Module] = []
        entity_map: dict[str, str] = {}
        adj: set[tuple[str, str]] = set()

        for cluster_id, entities in named.items():
            mod = Module(
                name=cluster_id,
                entities=sorted(entities),
                entity_count=len(entities),
                summary="",
            )
            modules.append(mod)
            for e in entities:
                entity_map[e] = mod.name

        # Cross-module adjacency from original edges
        for src_name, tgt_name in edges:
            sm = entity_map.get(src_name)
            tm = entity_map.get(tgt_name)
            if sm and tm and sm != tm:
                adj.add(tuple(sorted([sm, tm])))

        modules.sort(key=lambda m: -m.entity_count)
        return ModuleGraph(modules=modules, entity_to_module=entity_map, adjacency=sorted(adj))

    async def _fetch_edges(self, project_id: int) -> list[tuple[str, str]]:
        """Load ``(source_entity_name, target_entity_name)`` pairs."""
        from app.models.codebase import CodeEntity, CodeRelation, Repository, SourceFile

        async with session_scope() as session:
            rows = await session.execute(
                select(CodeRelation, CodeEntity, CodeEntity)
                .join(CodeEntity, CodeRelation.source_entity_id == CodeEntity.id)
                .join(CodeEntity, CodeRelation.target_entity_id == CodeEntity.id, isouter=True)
                .join(SourceFile, CodeEntity.file_id == SourceFile.id)
                .join(Repository, SourceFile.repository_id == Repository.id)
                .where(Repository.project_id == project_id)
                .where(CodeRelation.confidence.in_(["EXTRACTED", "INFERRED"]))
            )
            edges = []
            for rel, src, tgt in rows.all():
                if not src or not tgt:
                    continue
                edges.append((src.name, tgt.name))
        # Normalise (deduplicate, undirected)
        seen: set[tuple[str, str]] = set()
        result = []
        for a, b in edges:
            key = tuple(sorted([a, b]))
            if key not in seen:
                seen.add(key)
                result.append(key)
        return result

    def _empty_graph(self) -> ModuleGraph:
        return ModuleGraph(modules=[], entity_to_module={}, adjacency=[])

    async def _name_clusters(
        self, project_id: int, communities: dict[int, list[str]]
    ) -> dict[str, list[str]]:
        """Use LLM to give each cluster a human-readable name.

        Falls back to heuristic names when LLM is unavailable.
        """
        from app.domain.codebase.generation.leiden import name_clusters_with_llm
        return await name_clusters_with_llm(project_id, communities)

    def _log_gaps(self, communities: dict[int, list[str]], named: dict[str, list[str]]) -> None:
        unnamed = len(communities) - len(named)
        if unnamed > 0:
            logger.info("[ModuleGraph] %d cluster(s) fell back to heuristic names", unnamed)


# ── singleton ───────────────────────────────────────────────────────
module_graph_service = ModuleGraphService()
