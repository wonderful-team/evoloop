import asyncio, os, sys
os.environ['EMBEDDED_MODE'] = 'True'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

async def main():
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service
    evocloud_manager.initialize()
    login = await evocloud_manager.login("preterchan", "hellomylife")
    await identity_service.set_token(login["token"], login.get("refresh_token", ""))

    from sqlalchemy import select, delete
    from app.infrastructure.database import session_scope
    from app.models.codebase import Repository
    from app.models.app_map import AppMap

    async with session_scope() as session:
        await session.execute(delete(AppMap).where(AppMap.project_id == 121))
        await session.flush()

    import subprocess
    ref = "app/config/skills/app_map_analysis/scripts/reference_collector.py"
    r = subprocess.run(["uv", "run", "python", ref,
        "/Users/huangjinhuan/Projects/mall-backend",
        "--sql", "/Users/huangjinhuan/Projects/mall-backend/b2c_mall.sql"],
        capture_output=True, text=True, timeout=120,
        cwd="/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")
    for line in r.stdout.strip().split("\n"):
        if "Collect" in line or "collected" in line.lower():
            print(line)

    batch = "app/config/skills/app_map_analysis/scripts/batch_write_app_maps.py"
    r = subprocess.run(["uv", "run", "python", batch,
        "--project-id", "121", "--input", "/tmp/appmap_extracted.json"],
        capture_output=True, text=True, timeout=300,
        cwd="/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")
    for line in r.stdout.strip().split("\n"):
        if "Batch" in line or "status" in line.lower() or "written" in line.lower() or "complete" in line.lower():
            print(line)

    async with session_scope() as session:
        records = list((await session.execute(select(AppMap).where(AppMap.project_id == 121))).scalars().all())
        print(f"\nTotal AppMaps: {len(records)}")
        total_a = sum(len(r.actions) for r in records)
        total_e = sum(len(r.elements) for r in records)
        a_qual = sum(1 for r in records for a in r.actions if a.get("controller") and a.get("line"))
        e_qual = sum(1 for r in records for e in r.elements if e.get("page") and e.get("line"))
        print(f"Actions: {total_a} total, {a_qual} with controller+line ({a_qual/max(total_a,1)*100:.0f}%)")
        print(f"Elements: {total_e} total, {e_qual} with page+line ({e_qual/max(total_e,1)*100:.0f}%)")
        routes = sum(1 for r in records if r.routes)
        tables = sum(1 for r in records if r.db_tables)
        print(f"Entities with routes: {routes}/{len(records)}")
        print(f"Entities with db_tables: {tables}/{len(records)}")

        for r in records:
            if r.routes and r.db_tables and len(r.elements) > 5:
                print(f"\nSample: {r.entity}")
                print(f"  actions={len(r.actions)} elements={len(r.elements)} routes={len(r.routes)} tables={len(r.db_tables)}")
                print(f"  first action: {r.actions[0]['name']} kind={r.actions[0]['kind']} risk={r.actions[0]['risk_tier']}")
                print(f"  first element: {r.elements[0]['name']} selector={r.elements[0].get('selector_type','?')}")
                break

    await db_resource_manager.shutdown()

asyncio.run(main())
