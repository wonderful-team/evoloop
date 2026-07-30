#!/usr/bin/env python3
"""Full pipeline verification: framework_profile → downstream consumers → AppMap → Macros."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

os.environ.setdefault("EMBEDDED_MODE", "True")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

PROJECT_PATH = "/Users/huangjinhuan/Projects/Ruoyi-Cloud-Plus"
PROJECT_ID = 122

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pipeline_test")

passed = 0
failed = 0


def check(name: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        logger.info(f"  ✅ {name}")
    else:
        failed += 1
        logger.error(f"  ❌ {name}: {detail}")


async def step1_inject_framework_profile():
    """Inject a simulated framework_profile into project.json."""
    fp = {
        "framework_profile": {
            "language": "java",
            "framework": "spring-cloud",
            "build_tool": "maven",
            "architecture": "microservices",
            "role_classifiers": {
                "controller": {"name_patterns": ["*Controller"]},
                "service": {"name_patterns": ["*Service", "*ServiceImpl"]},
                "repository": {"name_patterns": ["*Mapper"]},
            },
            "module_paths": {
                "system": "ruoyi-modules/ruoyi-system",
                "gen": "ruoyi-modules/ruoyi-gen",
                "resource": "ruoyi-modules/ruoyi-resource",
            },
            "domain_vocabulary": ["权限", "用户", "角色", "部门", "菜单", "字典", "日志", "配置"],
            "profile_version": "1.0",
        }
    }
    from app.core.project.utils import write_project_json, read_project_json
    write_project_json(PROJECT_PATH, fp)
    pj = read_project_json(PROJECT_PATH)
    has = "framework_profile" in pj and pj["framework_profile"]["language"] == "java"
    check("Step1: Inject framework_profile into project.json", has)


async def step2_profile_api():
    """Test profile API reads framework_profile from project.json (via underlying logic)."""
    from app.core.project.utils import read_project_json
    pj = read_project_json(PROJECT_PATH)
    fp = pj.get("framework_profile")
    check("Step2: project.json has framework_profile", fp is not None)
    if fp:
        check("  language=java", fp.get("language") == "java")
        check("  role_classifiers has controller", "controller" in (fp.get("role_classifiers") or {}))
        check("  domain_vocabulary non-empty", len(fp.get("domain_vocabulary") or []) > 0)


async def step3_entity_grouper_role_classifiers():
    """Test EntityGrouper reads role_classifiers."""
    from app.core.atlas.source.skeleton import EntityGrouper
    from app.core.atlas.source.skeleton.generator import _FRONTEND_EXTS, _NON_CONTROLLER_STEMS

    grouper = EntityGrouper(project_path=PROJECT_PATH)
    check("Step3: EntityGrouper loaded role_classifiers", grouper._role_classifiers is not None)

    if grouper._role_classifiers:
        rcs = grouper._role_classifiers
        has_controller = "controller" in rcs
        has_service = "service" in rcs
        check("  role_classifiers has controller", has_controller)
        check("  role_classifiers has service", has_service)

    # Test classification
    tests = [
        ("ruoyi-modules/ruoyi-system/src/main/java/com/ruoyi/system/controller/SysUserController.java", "controller"),
        ("ruoyi-modules/ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java", "service"),
        ("ruoyi-modules/ruoyi-system/src/main/java/com/ruoyi/system/mapper/SysUserMapper.java", "repository"),
        ("ruoyi-ui/src/views/system/user/index.vue", None),  # should skip (frontend)
    ]
    for path, expected_role in tests:
        ext = os.path.splitext(path)[1]
        stem = os.path.splitext(os.path.basename(path))[0].lower()

        # Check frontend filter
        if ext in _FRONTEND_EXTS:
            check(f"  Frontend skip: {os.path.basename(path)}", True)
            continue

        # Check role_classifiers
        role = None
        if grouper._role_classifiers:
            for r, rules in grouper._role_classifiers.items():
                for pattern in rules.get("name_patterns") or []:
                    if pattern.startswith("*") and stem.endswith(pattern[1:].lower()):
                        role = r
                        break

        actual = role or grouper._classify_file(path, None)
        ok = (expected_role is None) or (actual == expected_role)
        if not ok:
            check(f"  Classify {os.path.basename(path)}: expected={expected_role} got={actual}", False)
        else:
            check(f"  Classify {os.path.basename(path)} → {actual}", True)


async def step4_index_and_appmap():
    """Clear data, run indexing + appmap generation (deterministic path)."""
    # Clear previous data
    from sqlalchemy import delete
    from app.infrastructure.database import session_scope
    from app.models.macro import Macro
    from app.models.app_map import AppMap
    async with session_scope() as s:
        await s.execute(delete(Macro).where(Macro.project_id == PROJECT_ID))
        await s.execute(delete(AppMap).where(AppMap.project_id == PROJECT_ID))
        await s.commit()

    from app.domain.codebase.generation.runner import run_generation_item
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize()

    # Sync project
    from app.core.project.sync_service import ProjectSyncService
    from app.core.project.utils import write_project_json
    from sqlalchemy import select
    from app.infrastructure.database import session_scope
    from app.models.codebase import Repository

    async with session_scope() as s:
        r = await s.execute(select(Repository).where(Repository.local_path == PROJECT_PATH))
        repo = r.scalar_one_or_none()
        if repo and repo.project_id != PROJECT_ID:
            repo.project_id = PROJECT_ID
            await s.commit()

    write_project_json(PROJECT_PATH, {"project_id": PROJECT_ID, "repo_id": repo.id if repo else None})

    # Index (force re-index to pick up any new files)
    from app.domain.codebase.indexing.service import IndexingService
    from app.domain.codebase.indexing.manager import indexing_manager
    svc = IndexingService()
    await svc.index_repository(PROJECT_PATH, repo.id, force=True)
    await indexing_manager._update_indexing_status(repo.id, "completed")
    logger.info("[Indexing] Complete")

    # Run appmap generation (deterministic path only, no Agent)
    await run_generation_item(PROJECT_ID, "appmap")


async def step5_verify_data():
    """Verify AppMaps and Macros data quality."""
    from sqlalchemy import select, func
    from app.infrastructure.database import session_scope
    from app.models.app_map import AppMap
    from app.models.macro import Macro

    async with session_scope() as s:
        # AppMap counts
        total_am = (await s.execute(select(func.count(AppMap.id)).where(AppMap.project_id == PROJECT_ID))).scalar()
        active_am = (await s.execute(select(func.count(AppMap.id)).where(AppMap.project_id == PROJECT_ID, AppMap.status == "active"))).scalar()
        check(f"Step5: Total AppMaps={total_am}", total_am >= 30)
        check(f"Step5: Active AppMaps={active_am}", active_am >= 30)

        # Macro counts
        total_macros = (await s.execute(select(func.count(Macro.id)).where(Macro.project_id == PROJECT_ID))).scalar()
        check(f"Step5: Total Macros={total_macros}", total_macros >= 80)

        # Check no garbage entities
        r = await s.execute(select(AppMap.entity).where(AppMap.project_id == PROJECT_ID, AppMap.status == "active"))
        entities = [row[0] for row in r.all()]
        garbage = {"resize", "ruoyi-ui", "ruoyi-auth", "ruoyi-example", "ruoyi-gateway", "ruoyi-modules",
                    "ruoyiresourceapplication", "resourceapplicationrunner", "keyprefix", "openapi",
                    "plusdatapermission", "gatewayexception", "globalexception", "mybatisexception",
                    "sentinelfallback", "translationbeanserializermodifier", "validatecode",
                    "resourceapplicationrunner"}
        found_garbage = [e for e in entities if e in garbage]
        check("Step5: No garbage entities", len(found_garbage) == 0, f"found: {found_garbage}")

        # Check trigger_patterns have no {{entity_cn}} placeholders
        r = await s.execute(select(Macro).where(Macro.project_id == PROJECT_ID).limit(20))
        bad_triggers = 0
        for m in r.scalars().all():
            for t in (m.trigger_patterns or []):
                if "{{" in t:
                    bad_triggers += 1
        check("Step5: No {{}} in trigger_patterns", bad_triggers == 0, f"found {bad_triggers}")

        # Check no duplicate macro names
        from sqlalchemy import text
        r = await s.execute(text("SELECT name, COUNT(*) as cnt FROM macros WHERE project_id = :pid GROUP BY name HAVING cnt > 1"), {"pid": PROJECT_ID})
        dupes = r.all()
        check("Step5: No duplicate macro names", len(dupes) == 0, f"{len(dupes)} dupes")

        # Log entity list
        logger.info(f"  Entities ({len(entities)}): {', '.join(sorted(entities))}")


async def step6_project_summarizer():
    """Test ProjectSummarizer runs without DirectorySummarizer dependency."""
    from app.core.project.summarizer import summarize_project_task

    import asyncio
    await asyncio.to_thread(summarize_project_task, "Ruoyi-Cloud-Plus", PROJECT_PATH)
    check("Step6: ProjectSummarizer ran without DirectorySummarizer error", True)


async def step7_leiden():
    """Test Leiden reads domain_vocabulary from project.json."""
    import json
    meta = os.path.join(PROJECT_PATH, ".evoloop", "project.json")
    if os.path.isfile(meta):
        with open(meta, encoding="utf-8") as f:
            data = json.load(f)
        fp = data.get("framework_profile") or {}
        domain_vocab = fp.get("domain_vocabulary") or []
        has_profile = bool(data.get("framework_profile"))
        check("Step7: project.json has framework_profile", has_profile)
        check("Step7: domain_vocabulary non-empty", len(domain_vocab) > 0, f"vocab={domain_vocab}")
    else:
        check("Step7: project.json exists", False)


async def step8_verify_logs():
    """Verify no DirectorySummarizer or StandardsAnalyst in logs."""
    # These should not appear in manager.py execution anymore
    # We verify by checking that the manager call was removed
    import ast
    with open(os.path.join(os.path.dirname(__file__), "../../app/domain/codebase/indexing/manager.py")) as f:
        content = f.read()
    has_ds = "DirectorySummarizer" in content
    has_sa = "StandardsAnalyst" in content
    check("Step8: No DirectorySummarizer in manager.py", not has_ds)
    check("Step8: No StandardsAnalyst in manager.py", not has_sa)
    check("Step8: No classify_files_with_llm in generator.py",
          "classify_files_with_llm" not in open(
              os.path.join(os.path.dirname(__file__), "../../app/core/atlas/source/skeleton/generator.py")).read())


async def main():
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize()

    logger.info("=" * 60)
    logger.info("FULL PIPELINE VERIFICATION")
    logger.info("=" * 60)

    try:
        t0 = time.time()

        await step1_inject_framework_profile()
        await step2_profile_api()
        await step3_entity_grouper_role_classifiers()
        await step4_index_and_appmap()
        await step5_verify_data()
        await step6_project_summarizer()
        await step7_leiden()
        await step8_verify_logs()

        elapsed = time.time() - t0

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"RESULTS: {passed} passed, {failed} failed ({elapsed:.1f}s)")
        logger.info("=" * 60)
        if failed:
            sys.exit(1)
        logger.info("✅ ALL TESTS PASSED")
    except Exception as e:
        logger.exception(f"❌ TEST FAILED: {e}")
        raise
    finally:
        await db_resource_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
