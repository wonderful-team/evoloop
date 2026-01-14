import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.api.routes.resources import (
    ResourceCreate,
    create_resource,
    delete_resource,
    list_resources,
)
from app.infrastructure.database.sql.database import get_db_session
from app.infrastructure.database.sql.models import ProjectResource


async def verify_resources_flow():
    print("🚀 Starting Resources End-to-End Verification...")

    # Setup: Assume Project ID 1 exists (or we use a dummy ID since we don't strictly enforce FK in this script,
    # but models might. Actually models.py says project_id is loose reference).
    PROJECT_ID = 999

    # 1. Clean verify state
    print(f"\n🧹 Cleaning up test resources for Project {PROJECT_ID}...")
    async with get_db_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(ProjectResource).where(ProjectResource.project_id == PROJECT_ID))
        await session.commit()

    # 2. Test Create Resource (Link)
    print("\n🧪 Testing Create Resource (External Link)...")
    link_req = ResourceCreate(
        type="link",
        name="Documentation",
        content="https://docs.example.com"
    )
    link_res = await create_resource(PROJECT_ID, link_req)
    print(f"✅ Created Link: {link_res.name} (ID: {link_res.id})")

    # 3. Test Create Resource (Pinned File)
    print("\n🧪 Testing Create Resource (Pinned File)...")
    file_req = ResourceCreate(
        type="file",
        name="README.md",
        content="README.md"
    )
    file_res = await create_resource(PROJECT_ID, file_req)
    print(f"✅ Created File: {file_res.name} (ID: {file_res.id})")

    # 4. Test List Resources
    print("\n🧪 Testing List Resources...")
    resources = await list_resources(PROJECT_ID)
    print(f"Found {len(resources)} resources.")
    for r in resources:
        print(f" - [{r.type}] {r.name}: {r.content}")

    assert len(resources) == 2
    assert any(r.type == 'link' and r.content == "https://docs.example.com" for r in resources)
    assert any(r.type == 'file' and r.content == "README.md" for r in resources)
    print("✅ List Verification Passed")

    # 5. Test Delete Resource
    print(f"\n🧪 Testing Delete Resource (ID: {link_res.id})...")
    await delete_resource(PROJECT_ID, link_res.id)

    resources_after = await list_resources(PROJECT_ID)
    print(f"Found {len(resources_after)} resources after delete.")
    assert len(resources_after) == 1
    assert resources_after[0].id == file_res.id
    print("✅ Delete Verification Passed")

    # 6. Test Idempotency (Pin same file twice)
    print("\n🧪 Testing Idempotency (Pin same file again)...")
    dup_res = await create_resource(PROJECT_ID, file_req)
    print(f"Result ID: {dup_res.id} (Should match original: {file_res.id})")
    assert dup_res.id == file_res.id

    resources_final = await list_resources(PROJECT_ID)
    assert len(resources_final) == 1
    print("✅ Idempotency Verification Passed")

    print("\n🎉 All Verification Steps Passed Successfully!")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Ensure DB is ready (normally done by app startup, but here we might need to init tables if simple script)
    # But since we are running in dev env where main.py likely ran before, tables exist.
    # We'll just run.
    loop.run_until_complete(verify_resources_flow())
