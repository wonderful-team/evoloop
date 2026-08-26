"""Project training orchestrator (v3.1).

train_project drives the pipeline for one project:
    phase 1  static seed:   indexing -> AppMap (reuse v2.0 generation runner)

Runtime macro verification was removed with the AppMap template chain; the
AppMap data layer (survey/collector) is retained.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def _phase1_static_seed(project_id: int) -> None:
    """indexing -> AppMap via the v2.0 generation runner (item='appmap')."""
    from app.domain.codebase.generation.runner import run_generation_item

    await run_generation_item(project_id, "appmap")
    logger.info("[train] phase1 (AppMap seed) done for project %s", project_id)


async def train_project(
    *,
    project_id: int,
    entity: str | None = None,
    skip_static_seed: bool = False,
) -> dict:
    """Train a project's operation library.

    Args:
        project_id: Target project.
        entity: Restrict to one entity (unused for static seed; retained for
            API signature compatibility).
        skip_static_seed: Skip phase 1 (indexing -> AppMap).

    Returns:
        Simple status dict.
    """
    if not skip_static_seed:
        await _phase1_static_seed(project_id)

    return {"project_id": project_id, "status": "appmap_seeded"}
