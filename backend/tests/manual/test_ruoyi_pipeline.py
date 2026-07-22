#!/usr/bin/env python3
"""Test the unified scanning pipeline against Ruoyi-Cloud-Plus (Java Spring)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

os.environ.setdefault("EMBEDDED_MODE", "True")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

PROJECT_PATH = "/Users/huangjinhuan/Projects/Ruoyi-Cloud-Plus"
WORKSPACE_ROOT = "/Users/huangjinhuan/Projects"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ruoyi_test")


async def _sync_project() -> tuple[int, int]:
    from sqlalchemy import select
    from app.core.project.sync_service import ProjectSyncService
    from app.core.project.utils import write_project_json
    from app.infrastructure.database import session_scope
    from app.models.codebase import Repository

    async with session_scope() as session:
        result = await session.execute(
            select(Repository).where(
                Repository.sync_status.in_(["SYNCED", "PENDING_CREATION"])
            )
        )
        for repo in result.scalars().all():
            if repo.local_path and PROJECT_PATH.startswith(repo.local_path.rstrip("/") + "/"):
                logger.warning(f"Ignoring conflicting ancestor repo: {repo.name}")
                repo.sync_status = "IGNORED"
                session.add(repo)

    repo: Repository | None = None
    async with session_scope() as session:
        result = await session.execute(
            select(Repository).where(Repository.local_path == PROJECT_PATH)
        )
        repo = result.scalar_one_or_none()
        if repo and repo.sync_status in ("IGNORED", "DISCONNECTED"):
            repo.sync_status = "PENDING_CREATION"
            session.add(repo)
        await session.commit()
        if repo:
            await session.refresh(repo)

    if repo is None:
        sync_service = ProjectSyncService()
        logger.info(f"Importing / syncing project at {PROJECT_PATH}...")
        repo = await sync_service.import_project_by_path(PROJECT_PATH, workspace_root=WORKSPACE_ROOT)

    from app.core.evocloud import evocloud_manager
    evocloud_manager.invalidate_projects_cache()
    cloud_projects = await evocloud_manager.scan_projects()
    project_id: int | None = None
    for p in cloud_projects:
        if p.get("path") == PROJECT_PATH or "ruoyi" in p.get("name", "").lower():
            project_id = int(p.get("id") or p.get("project_id") or 0) or None
            break

    if project_id is None:
        raise RuntimeError("Cloud project not found after import")

    async with session_scope() as session:
        conflict = await session.execute(
            select(Repository).where(
                Repository.project_id == project_id, Repository.id != repo.id
            )
        )
        for other in conflict.scalars().all():
            other.project_id = None
            session.add(other)

        db_repo = await session.get(Repository, repo.id)
        db_repo.project_id = project_id
        db_repo.sync_status = "SYNCED"
        session.add(db_repo)
        await session.commit()
        await session.refresh(db_repo)

    write_project_json(PROJECT_PATH, {"project_id": project_id, "repo_id": repo.id})
    return db_repo.project_id, db_repo.id


async def _run_indexing(repo_id: int):
    from app.domain.codebase.indexing.service import IndexingService
    from app.domain.codebase.indexing.manager import indexing_manager

    logger.info("Running full indexing...")
    svc = IndexingService()
    await svc.index_repository(PROJECT_PATH, repo_id, force=True)
    await indexing_manager._update_indexing_status(repo_id, "completed")
    logger.info("Indexing complete.")


async def _run_appmap(project_id: int):
    from app.domain.codebase.generation.runner import run_generation_item
    await run_generation_item(project_id, "appmap")


async def _verify(project_id: int):
    from sqlalchemy import select, func, text
    from app.infrastructure.database import session_scope
    from app.models.macro import Macro
    from app.models.app_map import AppMap

    async with session_scope() as session:
        r = await session.execute(select(func.count(AppMap.id)).where(AppMap.project_id == project_id))
        appmap_count = r.scalar()

        r = await session.execute(select(func.count(Macro.id)).where(Macro.project_id == project_id))
        macro_count = r.scalar()

        logger.info(f"\n{'='*50}")
        logger.info(f"Project {project_id}: {appmap_count} AppMaps, {macro_count} Macros")
        logger.info(f"{'='*50}")

        r = await session.execute(
            select(AppMap).where(AppMap.project_id == project_id).limit(5)
        )
        for am in r.scalars().all():
            logger.info(f"  AppMap #{am.id}: entity={am.entity} "
                         f"routes={len(am.routes or [])} actions={len(am.actions or [])} ")

        r = await session.execute(text(
            "SELECT name, COUNT(*) as cnt FROM macros WHERE project_id = :pid GROUP BY name HAVING cnt > 1 ORDER BY cnt DESC"
        ), {"pid": project_id})
        dupes = r.all()
        if dupes:
            logger.info(f"\nDuplicate macro names ({len(dupes)}):")
            for name, cnt in dupes[:15]:
                logger.info(f'  "{name}" x{cnt}')
        else:
            logger.info("\nNo duplicate macro names")

        r = await session.execute(
            select(Macro).where(Macro.project_id == project_id).limit(8)
        )
        logger.info("\nSample macros:")
        for m in r.scalars().all():
            logger.info(f"  #{m.id} {m.name} | risk={m.risk_tier} entity={m.entity}")


async def main():
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize()

    # --- Cloud LLM setup (login → token → awaken → build graph) ---
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Logging in via EvoCloud...")
    evocloud_manager.initialize()
    login = await evocloud_manager.login("preterchan", "hellomylife")
    await identity_service.set_token(login["token"], login.get("refresh_token", ""))
    logger.info("[Test] Login successful")

    from app.core.environment import awaken
    logger.info("[Test] Awakening agent environment...")
    await awaken()
    logger.info("[Test] Agent environment ready.")

    from app.infrastructure.config.service import SystemConfigService
    SystemConfigService.set_value("LLM_MODEL", "deepseek-chat")
    SystemConfigService.set_value("LLM_CONFIG_TYPE", "platform")
    logger.info("[Test] LLM_MODEL set to deepseek-v4-flash")

    # Increase Worker max steps to give Agent enough budget for all entities
    from app.core.config import settings
    old_steps = settings.WORKER_AGENT_MAX_STEPS
    settings.WORKER_AGENT_MAX_STEPS = 150
    logger.info("[Test] WORKER_AGENT_MAX_STEPS increased from %s to 150", old_steps)

    logger.info(f"{'='*60}")
    logger.info("Ruoyi-Cloud-Plus — Unified Scanning Pipeline Test")
    logger.info(f"{'='*60}")
    logger.info(f"Project: {PROJECT_PATH}")

    try:
        start = time.time()
        project_id, repo_id = await _sync_project()
        logger.info(f"Resolved project_id={project_id}, repo_id={repo_id}")

        await _run_indexing(repo_id)
        await _run_appmap(project_id)
        await _verify(project_id)

        elapsed = time.time() - start
        logger.info(f"\nTotal time: {elapsed:.1f}s")
        logger.info("✅ PIPELINE TEST PASSED")
    except Exception as e:
        logger.exception(f"❌ TEST FAILED: {e}")
        raise
    finally:
        await db_resource_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
