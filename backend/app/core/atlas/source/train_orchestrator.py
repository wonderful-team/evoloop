"""Project training orchestrator (v3.1).

train_project drives the whole pipeline for one project:
    phase 1  static seed:   indexing -> AppMap (reuse v2.0 generation runner)
    phase 2  runtime verify: runtime_verify -> repair elements + re-synthesize
                             macros in place (v3.1 core)
    phase 3  status converge: runtime_verify already deactivates ungrounded
                             macros; nothing extra needed here

Design ref: docs/ATLAS_OPERATION_PATH_MAP_DESIGN.md (§6).
"""

from __future__ import annotations

import logging

from app.core.atlas.source import runtime_verify

logger = logging.getLogger(__name__)


async def _phase1_static_seed(project_id: int) -> None:
    """indexing -> AppMap via the v2.0 generation runner (item='appmap')."""
    from app.domain.codebase.generation.runner import run_generation_item

    await run_generation_item(project_id, "appmap")
    logger.info("[train] phase1 (AppMap seed) done for project %s", project_id)


async def _phase2_runtime_verify(
    project_id: int, entity: str | None, base_url: str | None
) -> dict:
    """Runtime-verify + repair elements, re-synthesize macros in place."""
    stats = await runtime_verify.run(
        project_id=project_id, entity=entity, base_url=base_url
    )
    logger.info("[train] phase2 (runtime verify) for project %s: %s", project_id, stats)
    return stats


async def train_project(
    *,
    project_id: int,
    entity: str | None = None,
    base_url: str | None = None,
    skip_static_seed: bool = False,
) -> dict:
    """Train a project's operation library.

    Args:
        project_id: Target project.
        entity: Restrict to one entity (None = all active AppMaps).
        base_url: Origin for relative list-page URLs (default: from
            AppMap.extra.base_url).
        skip_static_seed: Skip phase 1 (indexing -> AppMap). Use when AppMaps
            already exist and only runtime verification is wanted.

    Returns:
        {entity: runtime_verify stats}.
    """
    if not skip_static_seed:
        await _phase1_static_seed(project_id)

    stats = await _phase2_runtime_verify(project_id, entity, base_url)
    return {"project_id": project_id, "entities": stats}
