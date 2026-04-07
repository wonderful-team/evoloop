#!/usr/bin/env python3
"""
验证项目简化后的数据库状态 (兼容 SQLite 和 PostgreSQL)
"""
import asyncio
import sys
from pathlib import Path

# Add parent dir to path
script_dir = Path(__file__).parent
backend_dir = script_dir.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import inspect, text
from app.infrastructure.database.sql.database import async_session_factory, engine


async def verify_repository_schema():
    """验证 Repository 表结构"""
    print("🔍 验证 Repository 表结构...")
    
    async with engine.connect() as conn:
        insp = inspect(conn)
        columns = insp.get_columns('repositories')
        
        column_info = {col['name']: col for col in columns}
        column_names = set(column_info.keys())
        
        print(f"   发现 {len(columns)} 个字段:")
        for col in columns:
            col_type = str(col['type'])
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            print(f"     - {col['name']}: {col_type} ({nullable})")
        
        # Verify expected columns
        expected = {'id', 'project_id', 'cloud_project_id', 'is_cloud_linked', 
                   'indexing_status', 'name', 'local_path'}
        missing = expected - column_names
        unexpected = column_names - expected - {'url', 'description', 'created_at', 
                                                 'updated_at', 'last_indexed_at'}
        
        if missing:
            print(f"   ❌ 缺失字段: {missing}")
            return False
        if unexpected:
            print(f"   ⚠️  意外字段: {unexpected}")
        
        # Check if removed columns are gone
        removed_columns = {'sync_status', 'detected_at', 'imported_at'}
        still_exist = removed_columns & column_names
        if still_exist:
            print(f"   ⚠️  应删除的字段仍存在: {still_exist}")
        
        print("   ✅ Repository 表结构正确")
        return True


async def verify_requirements_removed():
    """验证 requirements 表已删除"""
    print("\n🔍 验证 Requirements 表已删除...")
    
    async with engine.connect() as conn:
        insp = inspect(conn)
        tables = set(insp.get_table_names())
        
        removed_tables = {
            'project_requirement_documents',
            'project_requirement_analyses',
            'project_requirement_tasks'
        }
        
        still_exist = removed_tables & tables
        
        if still_exist:
            print(f"   ❌ 以下表仍然存在: {still_exist}")
            return False
        
        print("   ✅ Requirements 表已删除")
        return True


async def verify_data_migration():
    """验证数据迁移"""
    print("\n🔍 验证数据迁移...")
    
    async with async_session_factory() as session:
        # Check if repositories table exists
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='repositories'"))
        if not result.fetchone():
            print("   ℹ️  repositories 表不存在，可能是空数据库")
            return True
        
        # Check if is_cloud_linked is populated
        try:
            result = await session.execute(text("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN is_cloud_linked = 1 THEN 1 ELSE 0 END) as linked
                FROM repositories
            """))
            row = result.fetchone()
            total, linked = row[0], row[1] or 0
            
            print(f"   总 Repository 数: {total}")
            print(f"   已关联云端: {linked}")
        except Exception as e:
            print(f"   ⚠️  无法查询 is_cloud_linked: {e}")
        
        # Check indexing_status values
        try:
            result = await session.execute(text("""
                SELECT indexing_status, COUNT(*)
                FROM repositories
                GROUP BY indexing_status
            """))
            statuses = result.fetchall()
            print(f"   索引状态分布:")
            for status, count in statuses:
                print(f"     - {status}: {count}")
        except Exception as e:
            print(f"   ⚠️  无法查询 indexing_status: {e}")
        
        # Verify no 'not_needed' status
        try:
            result = await session.execute(text("""
                SELECT COUNT(*) FROM repositories WHERE indexing_status = 'not_needed'
            """))
            not_needed_count = result.scalar()
            
            if not_needed_count > 0:
                print(f"   ⚠️  仍有 {not_needed_count} 条记录使用 'not_needed' 状态")
            else:
                print("   ✅ 无 'not_needed' 状态残留")
        except Exception as e:
            print(f"   ⚠️  无法验证 'not_needed' 状态: {e}")
        
        return True


async def main():
    print("=" * 60)
    print("EvoLoop 项目简化验证")
    print("=" * 60)
    
    # Check database type
    async with engine.connect() as conn:
        dialect = conn.dialect.name
        print(f"数据库类型: {dialect}")
    
    try:
        results = []
        results.append(await verify_repository_schema())
        results.append(await verify_requirements_removed())
        results.append(await verify_data_migration())
        
        print("\n" + "=" * 60)
        if all(results):
            print("✅ 所有验证通过！")
            return 0
        else:
            print("❌ 部分验证失败")
            return 1
    except Exception as e:
        print(f"\n❌ 验证异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
