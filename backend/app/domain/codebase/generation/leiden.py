"""Leiden community detection wrapper + LLM cluster naming.

Separated from ``module_graph.py`` so the heavy dependencies
(``graspologic``, ``InternalLLMService``) are isolated.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


# ═══════════════════════════════════════════════════════════════════
# Leiden
# ═══════════════════════════════════════════════════════════════════
def run_leiden(edges: list[tuple[str, str]]) -> dict[int, list[str]]:
    """Run Leiden community detection on an undirected graph.

    Returns ``{cluster_id: [entity_name, ...]}``.
    Returns an empty dict if ``graspologic`` is not installed.
    """
    try:
        from graspologic.partition import leiden
    except ImportError:
        logger.error("[Leiden] graspologic not installed; skipping clustering")
        return {}

    # Build node → int index
    nodes: dict[str, int] = {}
    for a, b in edges:
        nodes.setdefault(a, len(nodes))
        nodes.setdefault(b, len(nodes))

    if len(nodes) < 2:
        return {}

    # Build edge list for graspologic (src_idx, tgt_idx, weight=1)
    edge_list = [(nodes[a], nodes[b], 1.0) for a, b in edges]

    try:
        labels = leiden(
            graph=edge_list,
            random_seed=42,
        )
    except Exception as exc:
        logger.warning("[Leiden] clustering failed: %s", exc)
        return {}

    # Group by label
    communities: dict[int, list[str]] = {}
    rev = {v: k for k, v in nodes.items()}
    for idx, label in enumerate(labels):
        communities.setdefault(int(label), []).append(rev[idx])

    logger.info("[Leiden] Found %d communities from %d edges", len(communities), len(edges))
    return communities


# ═══════════════════════════════════════════════════════════════════
# LLM Naming
# ═══════════════════════════════════════════════════════════════════
async def name_clusters_with_llm(
    project_id: int,
    communities: dict[int, list[str]],
) -> dict[str, list[str]]:
    """Give each community a human-readable name via LLM.

    Returns ``{module_name: [entity, ...]}`` with the same entities
    as *communities* but keyed by the LLM-generated name.
    Falls back to a heuristic name when the LLM call fails.
    """
    from app.infrastructure.llm import InternalLLMService

    project_summary = ""
    try:
        from app.core.project.utils import get_project_path, read_project_json

        path = await get_project_path(project_id)
        if path:
            pj = read_project_json(path)
            project_summary = pj.get("description", "")
            fp = pj.get("framework_profile") or {}
            domain_vocab = fp.get("domain_vocabulary") or []
    except (OSError, ValueError):
        logger.warning("Failed to read .evoloop/project.json for domain vocabulary", exc_info=True)

    result: dict[str, list[str]] = {}

    for cid, entities in communities.items():
        if len(entities) == 1:
            result[_fallback_name(entities)] = entities
            continue

        prompt = (
            "You are a software documentation architect.\n\n"
            f"Project description: {project_summary}\n\n"
            f"Domain vocabulary (use these terms when they match): {', '.join(domain_vocab)}\n\n"
            "Given a cluster of tightly coupled code entities from the same project,\n"
            "infer the most likely **human-readable module name** for this cluster.\n\n"
            "## Code Entities in this Cluster:\n"
        )
        for e in entities:
            prompt += f"- {e}\n"
        prompt += (
            "\n## Rules:\n"
            "- Return exactly one short module name (3-6 words max).\n"
            "- Use the project's domain language, not implementation jargon.\n"
            "- Examples: 'User Authentication', 'Payment Processing'\n"
            "- Do NOT return a cluster number or generic label.\n\n"
            "Return only the module name string, nothing else."
        )

        try:
            response = await InternalLLMService.invoke(
                messages=[{"role": "user", "content": prompt}],
                purpose="module_naming",
                temperature=0.1,
                max_tokens=50,
            )
            name = response.content.strip()
            if not name or len(name) > 60:
                name = _fallback_name(entities)
        except Exception as exc:
            logger.warning("[Leiden] LLM naming failed for cluster %s: %s", cid, exc)
            name = _fallback_name(entities)

        result[name] = entities

    return result


def _fallback_name(entities: list[str]) -> str:
    """Heuristic module name when LLM is unavailable."""
    # Try common prefix
    if len(entities) == 1:
        return entities[0]
    prefix = _common_prefix([e.lower() for e in entities])
    if prefix and len(prefix) > 2:
        return prefix.capitalize()
    return f"Module_{entities[0]}"


def _common_prefix(names: list[str]) -> str:
    if not names:
        return ""
    shortest = min(names, key=len)
    for i, ch in enumerate(shortest):
        if not all(n[i] == ch for n in names):
            return shortest[:i]
    return shortest
