#!/usr/bin/env python3
"""
统一清除并重建索引脚本

功能：
1. 清除 Neo4j（File, Directory, CodeEntity, Concept, CodeChunk）
2. 清除 Postgres（code_chunks, code_relations, code_entities, source_files, repositories）
3. 删除 Vector 索引
4. 重新索引所有项目（使用并发优化）

使用方法：
    python scripts/reset_and_rebuild.py
    
    # 仅清除不重建
    python scripts/reset_and_rebuild.py --clean-only
    
    # 仅重建不清除
    python scripts/reset_and_rebuild.py --rebuild-only
"""

import asyncio
import argparse
import logging
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, text

from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.sql.database import session_scope, get_db_session
from app.models import Repository

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def clean_knowledge_base():
    """清除所有索引数据"""
    logger.info("=" * 70)
    logger.info("🧹 开始清除知识库...")
    logger.info("=" * 70)

    # 1. Neo4j Cleanup
    logger.info("→ 连接 Neo4j...")
    driver = await get_graph_db()
    async with driver.session() as session:
        # Delete all code-related nodes
        nodes_to_delete = [
            "File",
            "Directory", 
            "CodeEntity",
            "Concept",
            "CodeChunk",
            "API",
            "DBTable"
        ]
        
        for node_type in nodes_to_delete:
            try:
                # Use batched transactions to avoid MemoryPoolOutOfMemoryError
                query = f"MATCH (n:{node_type}) CALL {{ WITH n DETACH DELETE n }} IN TRANSACTIONS OF 10000 ROWS"
                await session.run(query)
                logger.info(f"  ✓ 已删除 Neo4j 节点: {node_type}")
            except Exception as e:
                logger.warning(f"  ⚠ Neo4j 删除 {node_type} 失败: {e}")

        # Drop vector indexes
        indexes_to_drop = ["concept_embeddings", "code_embeddings"]
        for idx in indexes_to_drop:
            try:
                await session.run(f"DROP INDEX {idx} IF EXISTS")
                logger.info(f"  ✓ 已删除向量索引: {idx}")
            except Exception as e:
                logger.warning(f"  ⚠ 删除索引 {idx} 失败: {e}")

    logger.info("✅ Neo4j 清理完成")

    # 2. Postgres Cleanup
    logger.info("→ 连接 Postgres...")
    async with get_db_session() as session:
        tables_to_truncate = [
            "code_chunks",
            "code_relations",
            "code_entities",
            "source_files",
            "tools"
        ]

        # Check for hard reset (Drop and Recreate)
        is_hard_reset = getattr(args, "hard", False)
        
        if is_hard_reset:
            logger.info("🔥 执行硬重置：物理删除并重建向量相关表以对齐维度...")
            from app.infrastructure.database.sql.database import engine, Base
            # Import models to ensure they are registered with Base metadata
            import app.models.codebase
            import app.models.learning
            import app.models.system
            
            tables_to_recreate = ["code_chunks", "learned_skills", "tools"]
            
            async with engine.begin() as conn:
                for table in tables_to_recreate:
                    logger.info(f"  → 正在删除表: {table}")
                    await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                
                def create_tables(sync_conn):
                    target_metadata = Base.metadata
                    target_metadata.create_all(sync_conn, tables=[
                        target_metadata.tables[t] for t in tables_to_recreate
                    ])
                
                await conn.run_sync(create_tables)
            logger.info("  ✓ 向量表结构已重建。")
        else:
            for table in tables_to_truncate:
                try:
                    await session.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
                    logger.info(f"  ✓ 已清空表: {table}")
                except Exception as e:
                    logger.warning(f"  ⚠ 清空表 {table} 失败 (可能不存在): {e}")

        await session.commit()

    logger.info("✅ Postgres 清理完成")
    logger.info("=" * 70)
    logger.info("✨ 知识库清理完成！")
    logger.info("=" * 70)


async def rebuild_indexes():
    """重新构建所有项目的索引（使用并发优化）"""
    logger.info("=" * 70)
    logger.info("🔨 开始重建索引（并发模式）...")
    logger.info("=" * 70)

    service = IndexingService()

    async with session_scope() as session:
        # 获取所有 repository
        stmt = select(Repository)
        result = await session.execute(stmt)
        repos = result.scalars().all()

        if not repos:
            logger.warning("⚠ 数据库中没有找到任何项目")
            return

        logger.info(f"📊 找到 {len(repos)} 个项目")

        # 索引所有项目
        for idx, repo in enumerate(repos, 1):
            logger.info("─" * 70)
            logger.info(f"[{idx}/{len(repos)}] 索引项目: {repo.name}")
            logger.info(f"  路径: {repo.local_path}")
            logger.info(f"  项目ID: {repo.project_id}")

            try:
                import time
                start_time = time.time()

                # 使用 force=True 强制重建
                await service.index_repository(repo.local_path, repo.id, force=True)

                elapsed = time.time() - start_time
                logger.info(f"  ✅ 索引成功! 耗时: {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"  ❌ 索引失败: {e}", exc_info=True)

    logger.info("=" * 70)
    logger.info("✨ 索引重建完成！")
    logger.info("=" * 70)


async def main(args):
    """主函数"""
    try:
        if not args.rebuild_only:
            await clean_knowledge_base()

        if not args.clean_only:
            await rebuild_indexes()

        logger.info("")
        logger.info("🎉 所有操作完成！")

    except Exception as e:
        logger.error(f"❌ 发生错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="统一清除并重建索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 清除并重建所有索引
  python scripts/reset_and_rebuild.py

  # 仅清除，不重建
  python scripts/reset_and_rebuild.py --clean-only

  # 仅重建，不清除
  python scripts/reset_and_rebuild.py --rebuild-only
        """
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="仅清除索引，不重建"
    )
    parser.add_argument(
        "--rebuild-only",
        action="store_true",
        help="仅重建索引，不清除"
    )
    parser.add_argument(
        "--hard",
        action="store_true",
        help="硬件重置：物理删除并重建向量表（用于解决维度冲突）"
    )

    args = parser.parse_args()

    if args.clean_only and args.rebuild_only:
        logger.error("❌ --clean-only 和 --rebuild-only 不能同时使用")
        sys.exit(1)

    asyncio.run(main(args))
