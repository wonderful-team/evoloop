#!/usr/bin/env python3
"""
应用项目简化相关的数据库迁移 (SQLite 兼容)
"""
import asyncio
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Add parent dir to path
script_dir = Path(__file__).parent
backend_dir = script_dir.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def backup_database(db_path: Path) -> Path:
    """备份数据库文件"""
    backup_path = db_path.parent / f"{db_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    print(f"✅ 数据库已备份到: {backup_path}")
    return backup_path


async def apply_migrations():
    """应用 migration"""
    from alembic import command
    from alembic.config import Config
    
    # Load alembic config
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    
    print("🔧 应用数据库迁移...")
    print("-" * 60)
    
    # Get current revision
    from alembic.script import ScriptDirectory
    from alembic.runtime import migration
    
    script = ScriptDirectory.from_config(alembic_cfg)
    
    with sessionmaker(bind=create_engine(alembic_cfg.get_main_option("sqlalchemy.url")))() as session:
        context = migration.MigrationContext.configure(session.connection())
        current_rev = context.get_current_revision()
        print(f"当前 revision: {current_rev}")
    
    # Show pending migrations
    heads = script.get_heads()
    print(f"目标 heads: {heads}")
    
    # Apply migrations
    try:
        command.upgrade(alembic_cfg, "+2")  # Apply 2 migrations
        print("\n✅ Migration 应用成功!")
    except Exception as e:
        print(f"\n❌ Migration 失败: {e}")
        raise


async def main():
    print("=" * 60)
    print("EvoLoop 项目简化 - 数据库迁移")
    print("=" * 60)
    
    # Check if using SQLite
    from app.core.config import settings
    
    db_url = str(settings.SQLALCHEMY_DATABASE_URI)
    print(f"数据库 URL: {db_url}")
    
    is_sqlite = db_url.startswith("sqlite")
    
    if is_sqlite:
        # Extract db path from URL
        db_path = Path(db_url.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", ""))
        if db_path.is_absolute():
            db_file = db_path
        else:
            db_file = backend_dir / db_path
        
        print(f"SQLite 数据库文件: {db_file}")
        
        if db_file.exists():
            print("\n📦 备份数据库...")
            backup_database(db_file)
        else:
            print("\n⚠️  数据库文件不存在，将创建新数据库")
    else:
        print("\n⚠️  非 SQLite 数据库，请手动备份")
        response = input("是否继续? (yes/no): ")
        if response.lower() != "yes":
            print("已取消")
            return 1
    
    # Apply migrations
    try:
        await apply_migrations()
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Verify
    print("\n" + "=" * 60)
    print("🔍 运行验证...")
    print("=" * 60)
    
    import subprocess
    result = subprocess.run(
        [sys.executable, str(script_dir / "verify_simplification.py")],
        capture_output=False
    )
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("✅ 所有步骤完成!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("⚠️  验证未通过，请检查")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
