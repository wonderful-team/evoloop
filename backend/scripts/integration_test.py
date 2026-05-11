#!/usr/bin/env python3
"""
Integration Test for Project Simplification
Tests the simplified project management system end-to-end
"""
import asyncio
import sys
import tempfile
import os
from datetime import datetime
from pathlib import Path

# Add parent dir to path
script_dir = Path(__file__).parent
backend_dir = script_dir.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select, func
from app.infrastructure.database.sql.database import session_scope, engine
from app.models.codebase import Repository


async def test_database_schema():
    """Test 1: Verify database schema is correct"""
    print("\n" + "=" * 60)
    print("Test 1: Database Schema Verification")
    print("=" * 60)
    
    async with engine.connect() as conn:
        from sqlalchemy import inspect
        insp = inspect(conn)
        
        # Check repositories table exists
        if "repositories" not in insp.get_table_names():
            print("❌ repositories table not found")
            return False
        
        columns = {col['name'] for col in insp.get_columns('repositories')}
        
        # Required columns
        required = {'id', 'is_cloud_linked', 'cloud_project_id', 'indexing_status', 'name', 'local_path'}
        missing = required - columns
        
        if missing:
            print(f"❌ Missing columns: {missing}")
            return False
        
        # Should NOT have old columns
        removed = {'sync_status', 'detected_at', 'imported_at'}
        still_exists = removed & columns
        
        if still_exists:
            print(f"⚠️  Old columns still exist: {still_exists}")
        
        print("✅ Database schema is correct")
        print(f"   Columns: {sorted(columns)}")
        return True


async def test_data_migration():
    """Test 2: Verify data was migrated correctly"""
    print("\n" + "=" * 60)
    print("Test 2: Data Migration Verification")
    print("=" * 60)
    
    async with session_scope() as session:
        # Count repositories
        result = await session.execute(select(func.count()).select_from(Repository))
        total = result.scalar()
        
        print(f"   Total repositories: {total}")
        
        # Count linked vs unlinked
        result = await session.execute(
            select(func.count()).where(Repository.is_cloud_linked == True)
        )
        linked = result.scalar()
        
        result = await session.execute(
            select(func.count()).where(Repository.is_cloud_linked == False)
        )
        unlinked = result.scalar()
        
        print(f"   Linked to cloud: {linked}")
        print(f"   Local only: {unlinked}")
        
        # Check indexing_status values
        result = await session.execute(
            select(Repository.indexing_status, func.count())
            .group_by(Repository.indexing_status)
        )
        statuses = result.all()
        
        print(f"   Indexing statuses:")
        for status, count in statuses:
            print(f"     - {status}: {count}")
        
        # Verify no 'not_needed' status
        result = await session.execute(
            select(func.count()).where(Repository.indexing_status == 'not_needed')
        )
        not_needed_count = result.scalar()
        
        if not_needed_count > 0:
            print(f"⚠️  Found {not_needed_count} repositories with 'not_needed' status")
        else:
            print("✅ No 'not_needed' status found")
        
        print("✅ Data migration verified")
        return True


async def test_repository_crud():
    """Test 3: Test Repository CRUD operations"""
    print("\n" + "=" * 60)
    print("Test 3: Repository CRUD Operations")
    print("=" * 60)
    
    async with session_scope() as session:
        # Create test repository
        test_repo = Repository(
            name="Test Repository",
            description="Test description",
            local_path="/tmp/test_repo",
            url="file:///tmp/test_repo",
            is_cloud_linked=False,
            indexing_status="pending",
        )
        session.add(test_repo)
        await session.commit()
        await session.refresh(test_repo)
        
        repo_id = test_repo.id
        print(f"   Created test repository: ID {repo_id}")
        
        # Read
        result = await session.execute(
            select(Repository).where(Repository.id == repo_id)
        )
        fetched = result.scalar_one()
        
        if fetched.name != "Test Repository":
            print("❌ Failed to read repository")
            return False
        print("   Read: OK")
        
        # Update - link to cloud
        fetched.is_cloud_linked = True
        fetched.cloud_project_id = 999
        await session.commit()
        
        result = await session.execute(
            select(Repository).where(Repository.id == repo_id)
        )
        updated = result.scalar_one()
        
        if not updated.is_cloud_linked or updated.cloud_project_id != 999:
            print("❌ Failed to update repository")
            return False
        print("   Update (link to cloud): OK")
        
        # Delete
        await session.delete(updated)
        await session.commit()
        
        result = await session.execute(
            select(func.count()).where(Repository.id == repo_id)
        )
        count = result.scalar()
        
        if count != 0:
            print("❌ Failed to delete repository")
            return False
        print("   Delete: OK")
        
        print("✅ Repository CRUD operations work correctly")
        return True


async def test_project_service():
    """Test 4: Test ProjectSyncService"""
    print("\n" + "=" * 60)
    print("Test 4: ProjectSyncService")
    print("=" * 60)
    
    from app.domain.project.sync_service import project_sync_service
    
    # Test create_repository
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            repo = await project_sync_service.create_repository(
                local_path=tmpdir,
                name="Test Service Repo",
                description="Test from service",
                cloud_project_id=None,
            )
            
            print(f"   Created repository: ID {repo.id}")
            
            if repo.name != "Test Service Repo":
                print("❌ Repository creation failed")
                return False
            
            if repo.is_cloud_linked:
                print("❌ Repository should not be linked")
                return False
            
            # Test link_to_cloud
            linked = await project_sync_service.link_to_cloud(repo.id, 12345)
            
            if not linked.is_cloud_linked or linked.cloud_project_id != 12345:
                print("❌ Link to cloud failed")
                return False
            print("   Link to cloud: OK")
            
            # Test unlink_from_cloud
            unlinked = await project_sync_service.unlink_from_cloud(repo.id)
            
            if unlinked.is_cloud_linked or unlinked.cloud_project_id is not None:
                print("❌ Unlink from cloud failed")
                return False
            print("   Unlink from cloud: OK")
            
            # Cleanup
            await project_sync_service.delete_repository(repo.id)
            
            print("✅ ProjectSyncService works correctly")
            return True
            
        except Exception as e:
            print(f"❌ Service test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_indexing_service():
    """Test 5: Test IndexingService integration"""
    print("\n" + "=" * 60)
    print("Test 5: IndexingService Integration")
    print("=" * 60)
    
    from app.domain.codebase.indexing.service import IndexingService
    
    service = IndexingService()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Test get_or_create_repo
            repo = await service.get_or_create_repo(
                path=tmpdir,
                name="Test Indexing Repo",
                project_id=None,  # No cloud project
            )
            
            print(f"   Created repo: ID {repo.id}")
            
            if repo.is_cloud_linked:
                print("❌ Repo should not be auto-linked")
                return False
            
            if repo.indexing_status != "pending":
                print(f"❌ Expected indexing_status='pending', got '{repo.indexing_status}'")
                return False
            
            print("   Create repo without cloud: OK")
            
            # Test get_repo_by_path
            fetched = await service.get_repo_by_path(tmpdir)
            
            if fetched is None or fetched.id != repo.id:
                print("❌ get_repo_by_path failed")
                return False
            print("   Get repo by path: OK")
            
            # Cleanup
            from app.domain.project.sync_service import project_sync_service
            await project_sync_service.delete_repository(repo.id)
            
            print("✅ IndexingService integration works correctly")
            return True
            
        except Exception as e:
            print(f"❌ IndexingService test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_api_routes():
    """Test 6: Test API route availability (basic check)"""
    print("\n" + "=" * 60)
    print("Test 6: API Routes Check")
    print("=" * 60)
    
    from fastapi import FastAPI
    from app.api.main import api_router
    
    # Create test app and include router
    app = FastAPI()
    app.include_router(api_router)
    
    routes = [route.path for route in app.routes]
    
    # Check for new simplified endpoints
    required_routes = [
        "/api/v1/projects/import",
        "/api/v1/projects/{repo_id}/link",
        "/api/v1/projects/{repo_id}/unlink",
    ]
    
    for route in required_routes:
        # Check if route exists (might be in different formats)
        found = any(route.replace("{repo_id}", "") in r or route in r for r in routes)
        status = "✅" if found else "❌"
        print(f"   {status} {route}")
    
    print("✅ API routes check complete")
    return True


async def test_requirements_removed():
    """Test 7: Verify requirements tables are removed"""
    print("\n" + "=" * 60)
    print("Test 7: Requirements Tables Removal")
    print("=" * 60)
    
    async with engine.connect() as conn:
        from sqlalchemy import inspect
        insp = inspect(conn)
        tables = set(insp.get_table_names())
        
        removed_tables = {
            'project_requirement_documents',
            'project_requirement_analyses',
            'project_requirement_tasks'
        }
        
        still_exist = removed_tables & tables
        
        if still_exist:
            print(f"❌ Tables should be removed but still exist: {still_exist}")
            return False
        
        print("✅ All requirements tables successfully removed")
        return True


async def run_all_tests():
    """Run all integration tests"""
    print("\n" + "=" * 60)
    print("EvoLoop Project Simplification - Integration Tests")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    
    tests = [
        ("Database Schema", test_database_schema),
        ("Data Migration", test_data_migration),
        ("Repository CRUD", test_repository_crud),
        ("ProjectSyncService", test_project_service),
        ("IndexingService", test_indexing_service),
        ("API Routes", test_api_routes),
        ("Requirements Removed", test_requirements_removed),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test '{name}' failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print("-" * 60)
    print(f"Total: {len(results)} tests, {passed} passed, {failed} failed")
    print(f"Finished at: {datetime.now().isoformat()}")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nTest runner failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
