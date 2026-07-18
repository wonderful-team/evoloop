"""Leiden graph community clustering + LLM naming layer for Wiki outline planning.

Flow:
1. Load CodeRelation edges from DB (confidence: EXTRACTED/INFERRED).
2. Build undirected edge list, deduplicate, apply symmetric weight.
3. Run Leiden clustering via graspologic.
4. For each community, collect contained CodeEntity names.
5. LLM names each community using project context for terminology consistency.
6. Return recommended Wiki outline (list of module names).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def recommend_wiki_outline(
    project_id: int,
    session: AsyncSession,
    *,
    resolution: float = 1.0,
    min_cluster_size: int = 2,
) -> list[dict[str, Any]]:
    """Generate a recommended Wiki outline via Leiden clustering + LLM naming.

    Args:
        project_id: Target project.
        session: Open async DB session.
        resolution: Leiden resolution (higher → more clusters).
        min_cluster_size: Clusters below this size are merged into "Other".

    Returns:
        List of ``{name, entity_count, entity_names}`` dicts sorted by size.
    """
    edges, node_names, repo_id = await _fetch_code_relation_graph(project_id, session)
    if not edges or not node_names:
        logger.info("[Leiden] No CodeRelation data for project %s", project_id)
        return []

    # Deduplicate and symmetrise edges → undirected weighted edge list.
    edge_map: dict[tuple[int, int], float] = {}
    for src, tgt in edges:
        if src == tgt:
            continue
        key = (src, tgt) if src < tgt else (tgt, src)
        edge_map[key] = edge_map.get(key, 0.0) + 1.0

    if not edge_map:
        return []
    edge_list = [(int(a), int(b), w) for (a, b), w in edge_map.items()]

    # Leiden
    communities = await _run_leiden(edge_list, resolution=resolution)
    if not communities:
        return []

    # Group by community id → list of node ids.
    cluster_map: dict[int, set[int]] = defaultdict(set)
    for node_id, community_id in communities.items():
        cluster_map[community_id].add(node_id)

    # Build named cluster list.
    node_id_to_name = dict(node_names)

    clusters: list[dict[str, Any]] = []
    unclustered_nodes: set[int] = set()
    for community_id, members in cluster_map.items():
        member_names = [
            node_id_to_name.get(nid, f"node_{nid}")
            for nid in members
            if nid in node_id_to_name
        ]
        if len(members) < min_cluster_size:
            unclustered_nodes.update(members)
            continue
        clusters.append({
            "community_id": community_id,
            "entity_count": len(members),
            "entity_names": sorted(member_names),
            "name": "",  # filled by LLM
        })

    # Merge unclustered into one group.
    if unclustered_nodes:
        names = [
            node_id_to_name.get(nid, f"node_{nid}")
            for nid in unclustered_nodes
            if nid in node_id_to_name
        ]
        clusters.append({
            "community_id": -1,
            "entity_count": len(unclustered_nodes),
            "entity_names": sorted(names),
            "name": "",
        })

    # Sort by size descending.
    clusters.sort(key=lambda c: c["entity_count"], reverse=True)

    # LLM naming layer.
    project_context = await _fetch_project_context(project_id, session)
    await _name_clusters_with_llm(clusters, project_context)

    return [
        {
            "name": c["name"],
            "entity_count": c["entity_count"],
            "entity_names": c["entity_names"],
        }
        for c in clusters
        if c["name"]
    ]


async def _fetch_code_relation_graph(
    project_id: int, session: AsyncSession
) -> tuple[list[tuple[int, int]], list[tuple[int, str]], int | None]:
    """Load CodeRelation edges + CodeEntity names for a project.

    Returns:
        (edges, node_names, repo_id)
        edges: list of (source_entity_id, target_entity_id)
        node_names: list of (entity_id, name)
    """
    from app.models.codebase import CodeEntity, CodeRelation, Repository, SourceFile

    # Find the first non-ignored repo.
    repo_stmt = (
        select(Repository.id)
        .where(
            Repository.project_id == project_id,
            Repository.sync_status.not_in(("IGNORED", "DISCONNECTED")),
        )
        .order_by(Repository.id)
        .limit(1)
    )
    repo_result = await session.execute(repo_stmt)
    repo_id: int | None = await repo_result.scalar_one_or_none()
    if repo_id is None:
        return [], [], None

    # Load CodeEntity names scoped to this repo.
    entity_stmt = (
        select(CodeEntity.id, CodeEntity.name)
        .join(SourceFile, CodeEntity.file_id == SourceFile.id)
        .where(SourceFile.repository_id == repo_id)
    )
    entity_result = await session.execute(entity_stmt)
    all_entities = await entity_result.all()
    entity_ids = {row[0] for row in all_entities}
    node_names = [(row[0], row[1]) for row in all_entities]

    # Load CodeRelation edges scoped to these entities.
    edge_stmt = (
        select(CodeRelation.source_entity_id, CodeRelation.target_entity_id)
        .where(
            CodeRelation.source_entity_id.in_(entity_ids),
            CodeRelation.target_entity_id.is_not(None),
            CodeRelation.target_entity_id.in_(entity_ids),
            CodeRelation.confidence.in_(("EXTRACTED", "INFERRED")),
        )
    )
    edge_result = await session.execute(edge_stmt)
    rows = await edge_result.all()
    edges = [(row[0], row[1]) for row in rows]

    return edges, node_names, repo_id


async def _run_leiden(
    edge_list: list[tuple[int, int, float]], resolution: float = 1.0
) -> dict[int, int]:
    """Run Leiden clustering on an undirected weighted edge list.

    Returns:
        Dict mapping node_id → community_id.
    """
    try:
        from graspologic.partition import leiden
    except ImportError:
        logger.error("[Leiden] graspologic not installed; skipping clustering")
        return {}

    try:
        communities = leiden(
            graph=edge_list,
            resolution=resolution,
            randomness=0.001,
            trials=10,
            check_directed=False,
        )
        return communities
    except Exception as e:
        logger.error("[Leiden] Clustering failed: %s", e)
        return {}


async def _name_clusters_with_llm(
    clusters: list[dict[str, Any]],
    project_context: str,
) -> None:
    """Assign a human-readable name to each cluster via LLM."""
    unclustered = [c for c in clusters if c["community_id"] == -1]
    main_clusters = [c for c in clusters if c["community_id"] != -1]

    for cluster in main_clusters:
        name = await _llm_name_cluster(cluster, project_context)
        cluster["name"] = name or _fallback_name(cluster)

    # Name the catch-all group.
    if unclustered:
        unclustered[0]["name"] = _fallback_name(unclustered[0])


async def _llm_name_cluster(
    cluster: dict[str, Any], project_context: str
) -> str | None:
    """Call the LLM to name a single cluster."""
    try:
        from app.infrastructure.config.service import SystemConfigService
        from app.infrastructure.llm import InternalLLMService

        model_name = SystemConfigService.get_value("LLM_MODEL")
        if not model_name:
            logger.warning("[Leiden] No LLM_MODEL configured; skipping LLM naming")
            return None

        system_prompt = (
            "You are a software documentation architect. "
            "Respond only with the module name, no explanations."
        )
        user_prompt = (
            "Given a cluster of tightly coupled code entities from the same software project, "
            "infer the most likely human-readable documentation module name for this cluster.\n\n"
            f"## Project Context:\n{project_context}\n\n"
            "## Code Entities in this Cluster:\n"
        )
        for name in cluster["entity_names"]:
            user_prompt += f"- {name}\n"
        user_prompt += (
            "\n## Rules:\n"
            "- Return exactly one short module name (3-6 words max).\n"
            "- Use the project's domain language, not implementation jargon.\n"
            '- Examples: "User Authentication & Permissions", "Payment Processing", "Project File Management"\n'
            '- Do NOT return a cluster number or generic label like "Module A".\n\n'
            "Return only the module name string, nothing else."
        )

        response = await InternalLLMService.invoke(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            purpose="leiden_cluster_naming",
            temperature=0.3,
            max_tokens=100,
            model_name=model_name,
        )
        content = response.content if hasattr(response, "content") else str(response)
        name = content.strip().strip('"').strip("'")
        if name and len(name) < 100:
            return name
        return None
    except Exception as e:
        logger.warning("[Leiden] LLM naming failed for cluster: %s", e)
        return None


def _fallback_name(cluster: dict[str, Any]) -> str:
    """Generate a fallback module name when LLM naming is unavailable."""
    names = cluster.get("entity_names", [])
    if not names:
        return "Other"
    # Use the longest common path prefix heuristic: pick the most generic name.
    prefixes = _common_prefixes(names)
    if prefixes:
        return prefixes[0].replace("_", " ").replace("-", " ").title()
    return "Other"


def _common_prefixes(names: list[str]) -> list[str]:
    """Extract common filename-style prefixes from entity names."""
    parts = [n.split(".") for n in names if "." in n]
    if not parts:
        return []
    # Find most common first-part.
    from collections import Counter
    first_parts = Counter(p[0] for p in parts if p)
    if first_parts:
        most_common = first_parts.most_common(1)[0][0]
        return [most_common]
    return []


async def _fetch_project_context(project_id: int, _session: AsyncSession) -> str:
    """Fetch available project context for LLM naming (directory summaries)."""
    try:
        from app.core.project.utils import get_project_path

        path = await get_project_path(project_id)
        if path:
            return f"Project path: {path}"
        return ""
    except Exception as e:
        logger.debug("[Leiden] Failed to fetch project path: %s", e)
        return ""
