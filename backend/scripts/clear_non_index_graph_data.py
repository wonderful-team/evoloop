"""
清除与文件索引无关的图数据
保留: File, Directory, CodeEntity
清除: App, State, User, Preference, Concept, Episode 及其关系

独立脚本，不依赖项目配置
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Neo4j 配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "admin888")


async def clear_non_index_data():
    """清除所有与文件索引无关的图数据."""
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        logger.error("请先安装 neo4j-driver: pip install neo4j-driver")
        return

    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # 定义要清除的节点标签（与文件索引无关的数据）
    labels_to_clear = [
        "Episode",      # 记忆片段
        "Concept",      # 概念
        "Preference",   # 偏好
        "User",         # 用户
        "State",        # Atlas 状态
        "App",          # Atlas 应用
        "Element",      # Atlas/UI 元素（残留的）
        "APIEndpoint",  # API 端点（可能残留的）
        "DBColumn",     # 数据库列（可能残留的）
    ]

    async with driver.session() as session:
        # 清除各类节点
        for label in labels_to_clear:
            try:
                # 先统计数量
                count_result = await session.run(f"MATCH (n:{label}) RETURN count(n) as cnt")
                count_record = await count_result.single()
                node_count = count_record["cnt"] if count_record else 0

                if node_count > 0:
                    # 清除节点及其关系
                    result = await session.run(
                        f"MATCH (n:{label}) CALL {{ WITH n DETACH DELETE n }} IN TRANSACTIONS OF 10000 ROWS"
                    )
                    summary = await result.consume()
                    logger.info(f"✅ 清除 {label}: {summary.counters.nodes_deleted} 个节点, {summary.counters.relationships_deleted} 个关系")
                else:
                    logger.info(f"ℹ️  {label}: 无数据")
            except Exception as e:
                logger.warning(f"⚠️ 清除 {label} 时出错: {e}")

        # 清除残留关系（不属于 File/Directory/CodeEntity 的关系）
        try:
            result = await session.run("""
                MATCH ()-[r]-()
                WHERE NOT (startNode(r):File OR startNode(r):Directory OR startNode(r):CodeEntity)
                   OR NOT (endNode(r):File OR endNode(r):Directory OR endNode(r):CodeEntity)
                WITH r LIMIT 10000
                DELETE r
                RETURN count(r) as deleted
            """)
            summary = await result.consume()
            if summary.counters.relationships_deleted > 0:
                logger.info(f"✅ 清除残留关系: {summary.counters.relationships_deleted} 个")
        except Exception as e:
            logger.debug(f"清除残留关系时出错（可能无残留）: {e}")

        # 统计剩余数据
        try:
            result = await session.run("""
                MATCH (n)
                RETURN labels(n)[0] as label, count(n) as count
                ORDER BY label
            """)
            records = await result.data()
            logger.info("\n📊 清理后图数据库中的节点统计:")
            if records:
                for record in records:
                    logger.info(f"   - {record['label']}: {record['count']} 个节点")
            else:
                logger.info("   （数据库为空）")
        except Exception as e:
            logger.error(f"统计失败: {e}")

    await driver.close()


async def main():
    logger.info("=" * 60)
    logger.info("开始清除与文件索引无关的图数据...")
    logger.info("保留: File, Directory, CodeEntity")
    logger.info("清除: App, State, User, Preference, Concept, Episode")
    logger.info(f"Neo4j: {NEO4J_URI}")
    logger.info("=" * 60)

    try:
        await clear_non_index_data()
        logger.info("\n✅ 清理完成！")
    except Exception as e:
        logger.error(f"❌ 清理失败: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
