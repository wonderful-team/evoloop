#!/usr/bin/env python3
"""
EvoLoop 系统清理脚本
====================

EvoLoop 后端综合清理工具，可清理以下内容：
- Keychain 登录凭据（cloud_token, device_key, member_id）
- Redis 缓存（上下文、意图缓存、动态应用跟踪）
- Neo4j 图数据库（文件、目录、代码实体、概念、代码块、执行记录、偏好设置、用户节点）
- PostgreSQL 表（文件索引、向量存储、技能、跟踪记录、消息、任务）
- 文件系统产物（截图、屏幕录制、知识库、大脑记忆）

用法：
    # 试运行 - 预览将被删除的内容
    python scripts/cleanup_system.py --dry-run

    # 清理指定组件
    python scripts/cleanup_system.py --redis --neo4j --skills

    # 清理所有内容（警告：不可恢复！）
    python scripts/cleanup_system.py --all

    # 带确认提示的清理
    python scripts/cleanup_system.py --all --confirm

    # 仅清理过期数据，保留近期数据
    python scripts/cleanup_system.py --expired-only

    # 清理 Keychain 登录凭据
    python scripts/cleanup_system.py --keychain

作者：EvoLoop System
"""

import argparse
import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cleanup")

# 将父目录添加到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent))


class CleanupStats:
    """追踪清理统计数据。"""

    def __init__(self):
        self.redis_keys_deleted = 0
        self.neo4j_nodes_deleted = 0
        self.postgres_rows_deleted = 0
        self.files_deleted = 0
        self.directories_removed = 0
        self.storage_freed_mb = 0.0
        self.errors: list[str] = []

    def print_summary(self):
        """打印清理摘要。"""
        print("\n" + "=" * 60)
        print("📊 清理摘要")
        print("=" * 60)
        print(f"  已删除 Redis 键:      {self.redis_keys_deleted}")
        print(f"  已删除 Neo4j 节点:    {self.neo4j_nodes_deleted}")
        print(f"  已删除 PostgreSQL 行:  {self.postgres_rows_deleted}")
        print(f"  已删除文件:           {self.files_deleted}")
        print(f"  已删除目录:           {self.directories_removed}")
        print(f"  已释放存储空间:       {self.storage_freed_mb:.2f} MB")

        if self.errors:
            print(f"\n  ⚠️  遇到的错误: {len(self.errors)}")
            for err in self.errors[:5]:
                print(f"     - {err}")
            if len(self.errors) > 5:
                print(f"     ... 还有 {len(self.errors) - 5} 个")

        print("=" * 60)


class CleanupManager:
    """管理所有清理操作。"""

    def __init__(self, dry_run: bool = False, confirm: bool = False):
        self.dry_run = dry_run
        self.confirm = confirm
        self.stats = CleanupStats()

        # 导入设置
        from app.core.config import settings

        self.settings = settings

    def _confirm(self, message: str) -> bool:
        """请求用户确认。"""
        if not self.confirm:
            return True
        response = input(f"{message} [y/N]: ").strip().lower()
        return response in ("y", "yes")

    async def cleanup_redis(self) -> bool:
        """
        清理 Redis 缓存。
        键模式：
        - evo:context:{thread_id} - 线程执行上下文
        - evo:intent_cache:{hash} - 意图匹配缓存
        - system:dynamic_apps:{platform} - 动态应用分类
        - system:processed_apps:{platform} - 已处理应用跟踪
        - system:app_categorization:{platform} - 应用推理数据
        """
        print("\n🔴 REDIS 清理")
        print("-" * 40)

        try:
            import redis.asyncio as redis_lib

            from app.infrastructure.database.redis import redis_client

            # 检查连接
            try:
                await redis_client.ping()
            except Exception as e:
                logger.error(f"无法连接到 Redis：{e}")
                self.stats.errors.append(f"Redis 连接: {e}")
                return False

            # 定义要清理的键模式
            patterns = [
                "evo:context:*",
                "evo:intent_cache:*",
                "system:dynamic_apps:*",
                "system:processed_apps:*",
                "system:app_categorization:*",
            ]

            total_keys = 0
            for pattern in patterns:
                keys = await redis_client.keys(pattern)
                if keys:
                    total_keys += len(keys)
                    if not self.dry_run:
                        if len(keys) == 1:
                            await redis_client.delete(keys[0])
                        elif keys:
                            await redis_client.delete(*keys)
                    logger.info(f"  {pattern}: {len(keys)} 个键")
                else:
                    logger.info(f"  {pattern}: 0 个键")

            self.stats.redis_keys_deleted = total_keys

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {total_keys} 个 Redis 键")
            return True

        except ImportError as e:
            logger.warning(f"  ⚠️  Redis 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ Redis 清理失败：{e}")
            self.stats.errors.append(f"Redis: {e}")
            return False

    async def cleanup_neo4j_index(self, keep_apps: bool = False) -> bool:
        """
        清理 Neo4j 文件索引节点（代码库索引数据）。

        节点类型：
        - File - 代码库索引中的文件引用
        - Directory - 目录结构
        - CodeEntity - 代码符号/实体
        - CodeChunk - 向量化代码块
        - App, State - Atlas 数据（可选：保留应用）
        """
        print("\n🟣 NEO4J 文件索引清理")
        print("-" * 40)

        try:
            from app.infrastructure.database.graph.driver import get_graph_db

            driver = await get_graph_db()

            # 获取删除前的计数
            async with driver.session() as session:
                node_types = [
                    "File",
                    "Directory",
                    "CodeEntity",
                    "CodeChunk",
                ]

                if not keep_apps:
                    node_types.extend(["State", "App"])

                total_nodes = 0
                for node_type in node_types:
                    result = await session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                    record = await result.single()
                    count = record["count"] if record else 0
                    total_nodes += count
                    logger.info(f"  {node_type}: {count} 个节点")

                # 删除前确认
                if total_nodes > 0 and not self._confirm(
                    f"Delete {total_nodes} file index nodes from Neo4j?"
                ):
                    print("  ⏭️  已跳过")
                    return True

                if not self.dry_run:
                    # 分批删除节点以避免内存溢出
                    for node_type in node_types:
                        try:
                            deleted = await self._delete_nodes_in_batches(session, node_type)
                            logger.info(f"  已删除 {deleted} 个 {node_type} 节点")
                        except Exception as e:
                            logger.warning(f"  删除 {node_type} 失败：{e}")

                self.stats.neo4j_nodes_deleted += total_nodes

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {total_nodes} 个文件索引节点")
            return True

        except ImportError as e:
            logger.warning(f"  ⚠️  Neo4j 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ Neo4j 索引清理失败：{e}")
            self.stats.errors.append(f"Neo4j 索引: {e}")
            return False

    async def _delete_nodes_in_batches(self, session, node_type: str, batch_size: int = 1000) -> int:
        """分批删除节点以避免 Neo4j 内存溢出。"""
        total_deleted = 0
        while True:
            # 使用 LIMIT 分批删除
            result = await session.run(
                f"MATCH (n:{node_type}) WITH n LIMIT $batch_size DETACH DELETE n RETURN count(n) as deleted",
                batch_size=batch_size
            )
            record = await result.single()
            deleted = record["deleted"] if record else 0
            total_deleted += deleted

            if deleted < batch_size:
                # 删除数量小于批次大小，说明已删除完毕
                break

            # 每批次后短暂暂停，让 Neo4j 有机会回收内存
            await asyncio.sleep(0.1)

        return total_deleted

    async def cleanup_neo4j_memory(self) -> bool:
        """
        清理 Neo4j 记忆节点（长期记忆数据）。

        节点类型：
        - Concept - 知识概念（语义记忆）
        - Episode - 执行历史（情景记忆）
        - Preference - 用户偏好
        - User - 用户实体

        向量索引：
        - concept_embeddings - 概念向量索引
        - episode_embeddings - 执行记录向量索引
        """
        print("\n🟣 NEO4J 记忆清理")
        print("-" * 40)

        try:
            from app.infrastructure.database.graph.driver import get_graph_db

            driver = await get_graph_db()

            # 获取删除前的计数
            async with driver.session() as session:
                node_types = [
                    ("Concept", "知识概念"),
                    ("Episode", "执行历史"),
                    ("Preference", "用户偏好"),
                    ("User", "用户实体"),
                ]

                total_nodes = 0
                for node_type, description in node_types:
                    result = await session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                    record = await result.single()
                    count = record["count"] if record else 0
                    total_nodes += count
                    logger.info(f"  {node_type} ({description}): {count} 个节点")

                # 删除前确认
                if total_nodes > 0 and not self._confirm(
                    f"Delete {total_nodes} memory nodes from Neo4j?\n"
                    "  (This includes concepts, episodes, preferences, and user data)"
                ):
                    print("  ⏭️  已跳过")
                    return True

                if not self.dry_run:
                    # 分批删除节点以避免内存溢出
                    for node_type, _ in node_types:
                        try:
                            deleted = await self._delete_nodes_in_batches(session, node_type)
                            logger.info(f"  已删除 {deleted} 个 {node_type} 节点")
                        except Exception as e:
                            logger.warning(f"  删除 {node_type} 失败：{e}")

                    # 删除向量索引
                    try:
                        await session.run("DROP INDEX concept_embeddings IF EXISTS")
                        await session.run("DROP INDEX episode_embeddings IF EXISTS")
                        logger.info("  已删除记忆向量索引")
                    except Exception as e:
                        logger.warning(f"  删除索引失败：{e}")

                self.stats.neo4j_nodes_deleted += total_nodes

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {total_nodes} 个记忆节点")
            return True

        except ImportError as e:
            logger.warning(f"  ⚠️  Neo4j 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ Neo4j 记忆清理失败：{e}")
            self.stats.errors.append(f"Neo4j 记忆: {e}")
            return False

    async def cleanup_skills(self) -> bool:
        """
        清理所有技能相关数据。

        数据库表：
        - learned_skills - 已学习/自动化的技能
        - trace_events - 模仿学习执行跟踪
        - router_training_data - 意图路由示例

        文件：
        - ~/.evoloop/skills/ - 物理技能文件 (SKILL.md)
        """
        print("\n🔵 技能清理")
        print("-" * 40)

        # 步骤 1：清理数据库表
        tables = ["learned_skills", "trace_events", "router_training_data"]
        db_success = True

        try:
            from sqlalchemy import text

            from app.infrastructure.database.sql.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                total_rows = 0

                for table in tables:
                    try:
                        result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar() or 0
                        total_rows += count
                        logger.info(f"  {table}: {count} 行")

                        if not self.dry_run and count > 0:
                            await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    except Exception as e:
                        logger.warning(f"  清理 {table} 失败：{e}")

                if not self.dry_run:
                    await session.commit()

                self.stats.postgres_rows_deleted += total_rows

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {total_rows} 行技能表数据")

        except ImportError as e:
            logger.warning(f"  ⚠️  PostgreSQL 不可用：{e}")
            db_success = False
        except Exception as e:
            logger.error(f"  ❌ PostgreSQL 技能清理失败：{e}")
            self.stats.errors.append(f"PostgreSQL 技能: {e}")
            db_success = False

        # 步骤 2：清理技能文件
        print("\n📁 技能文件清理")
        print("-" * 40)

        try:
            skills_dir = self.settings.SKILLS_DIR

            if not os.path.exists(skills_dir):
                print("  ℹ️  技能目录不存在")
                return db_success

            # 统计文件数量
            file_count = 0
            total_size = 0
            for root, dirs, files in os.walk(skills_dir):
                for file in files:
                    file_count += 1
                    filepath = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(filepath)
                    except:
                        pass

            dir_count = sum(1 for _, dirs, _ in os.walk(skills_dir) for d in dirs)

            if file_count == 0:
                print("  ℹ️  没有技能文件需要清理")
                return db_success

            if not self._confirm(f"删除 {file_count} 个技能文件 ({total_size / (1024 * 1024):.2f} MB)?"):
                print("  ⏭️  已跳过")
                return db_success

            if not self.dry_run:
                shutil.rmtree(skills_dir, ignore_errors=True)
                os.makedirs(skills_dir, exist_ok=True)

            self.stats.files_deleted += file_count
            self.stats.directories_removed += dir_count
            self.stats.storage_freed_mb += total_size / (1024 * 1024)

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {file_count} 个技能文件")
            return True

        except Exception as e:
            logger.error(f"  ❌ 技能文件清理失败：{e}")
            self.stats.errors.append(f"技能文件: {e}")
            return False

    async def cleanup_postgres_index(self) -> bool:
        """
        清理文件索引和向量存储 PostgreSQL 表。

        表：
        - project_resources - 项目资源（固定文件、外部链接）
        - wikipage - 项目 Wiki 页面
        - repositories - Git 仓库元数据
        - source_files - 已索引的源文件
        - code_chunks - 向量化代码块
        - code_entities - 代码符号/实体
        - code_relations - 实体间关系
        - tools - 工具嵌入向量
        """
        print("\n🔵 POSTGRESQL 索引清理")
        print("-" * 40)

        tables = [
            "project_resources",
            "wikipage",
            "repositories",
            "source_files",
            "code_chunks",
            "code_entities",
            "code_relations",
            "tools",
        ]

        try:
            from sqlalchemy import text

            from app.infrastructure.database.sql.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                total_rows = 0

                for table in tables:
                    try:
                        result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar() or 0
                        total_rows += count
                        logger.info(f"  {table}: {count} 行")

                        if not self.dry_run and count > 0:
                            await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    except Exception as e:
                        logger.warning(f"  清理 {table} 失败：{e}")

                if not self.dry_run:
                    await session.commit()

                self.stats.postgres_rows_deleted += total_rows

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {total_rows} 行索引表数据")
            return True

        except ImportError as e:
            logger.warning(f"  ⚠️  PostgreSQL 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ PostgreSQL 索引清理失败：{e}")
            self.stats.errors.append(f"PostgreSQL 索引: {e}")
            return False

    async def cleanup_postgres_messages(self) -> bool:
        """
        从 PostgreSQL 清理对话消息。

        表：
        - messages - 聊天消息
        - conversations - 对话线程
        """
        print("\n🔵 POSTGRESQL 消息清理")
        print("-" * 40)

        tables = ["messages", "conversations"]

        try:
            from sqlalchemy import text

            from app.infrastructure.database.sql.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                total_rows = 0

                for table in tables:
                    try:
                        result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar() or 0
                        total_rows += count
                        logger.info(f"  {table}: {count} 行")

                        if not self.dry_run and count > 0:
                            await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    except Exception as e:
                        logger.warning(f"  清理 {table} 失败：{e}")

                if not self.dry_run:
                    await session.commit()

                self.stats.postgres_rows_deleted += total_rows

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {total_rows} 行消息表数据")
            return True

        except ImportError as e:
            logger.warning(f"  ⚠️  PostgreSQL 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ PostgreSQL 消息清理失败：{e}")
            self.stats.errors.append(f"PostgreSQL 消息: {e}")
            return False

    async def cleanup_postgres_jobs(self) -> bool:
        """
        从 PostgreSQL 清理任务队列。

        表：
        - jobs - 后台任务队列
        """
        print("\n🔵 POSTGRESQL 任务清理")
        print("-" * 40)

        try:
            from sqlalchemy import text

            from app.infrastructure.database.sql.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                result = await session.execute(text("SELECT COUNT(*) FROM jobs"))
                count = result.scalar() or 0
                logger.info(f"  jobs: {count} 行")

                if not self.dry_run and count > 0:
                    await session.execute(text("TRUNCATE TABLE jobs CASCADE"))
                    await session.commit()

                self.stats.postgres_rows_deleted += count

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {count} 个任务")
            return True

        except ImportError as e:
            logger.warning(f"  ⚠️  PostgreSQL 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ PostgreSQL 任务清理失败：{e}")
            self.stats.errors.append(f"PostgreSQL 任务: {e}")
            return False

    def cleanup_screenshots(self, expired_only: bool = False) -> bool:
        """
        清理截图存储。

        目录：
        - ~/.evoloop/artifacts/screenshots/temp/ - 临时截图（保留 1 天）
        - ~/.evoloop/artifacts/screenshots/atlas/ - Atlas 学习截图（保留 90 天）
        - ~/.evoloop/artifacts/screenshots/debug/ - 调试图（保留 7 天）
        - ~/.evoloop/artifacts/screenshots/dataset/ - 数据集截图（保留 365 天）
        """
        print("\n📸 截图清理")
        print("-" * 40)

        try:
            from app.core.vision.storage import screenshot_storage

            if expired_only:
                stats = screenshot_storage.cleanup_expired(dry_run=self.dry_run)
                total = sum(stats.values())
                self.stats.files_deleted += total

                action = "将清理" if self.dry_run else "已清理"
                print(f"  ✅ {action} {total} 个过期截图")
                for purpose, count in stats.items():
                    if count > 0:
                        print(f"     - {purpose}: {count}")
            else:
                # 清理所有截图
                base_dir = self.settings.SCREENSHOTS_DIR

                if not os.path.exists(base_dir):
                    print("  ℹ️  截图目录不存在")
                    return True

                # 统计文件数量 first
                file_count = 0
                total_size = 0
                for root, dirs, files in os.walk(base_dir):
                    for file in files:
                        if file.endswith((".png", ".jpg", ".jpeg")):
                            file_count += 1
                            filepath = os.path.join(root, file)
                            try:
                                total_size += os.path.getsize(filepath)
                            except:
                                pass

                dir_count = sum(1 for _, dirs, _ in os.walk(base_dir) for d in dirs)

                if file_count == 0:
                    print("  ℹ️  没有截图需要清理")
                    return True

                if not self._confirm(f"删除 {file_count} 个截图 ({total_size / (1024 * 1024):.2f} MB)?"):
                    print("  ⏭️  已跳过")
                    return True

                if not self.dry_run:
                    shutil.rmtree(base_dir, ignore_errors=True)
                    os.makedirs(base_dir, exist_ok=True)

                self.stats.files_deleted += file_count
                self.stats.directories_removed += dir_count
                self.stats.storage_freed_mb += total_size / (1024 * 1024)

                action = "将删除" if self.dry_run else "已删除"
                print(f"  ✅ {action} {file_count} 个截图 ({total_size / (1024 * 1024):.2f} MB)")

            return True

        except Exception as e:
            logger.error(f"  ❌ 截图清理失败：{e}")
            self.stats.errors.append(f"截图: {e}")
            return False

    def cleanup_recordings(self, expired_only: bool = False) -> bool:
        """
        清理屏幕录制存储。

        目录：
        - ~/.evoloop/artifacts/recordings/ - 屏幕录制视频
        - ~/.evoloop/artifacts/recordings/frames/ - 提取的帧
        """
        print("\n🎥 屏幕录制清理")
        print("-" * 40)

        try:
            from app.core.vision.storage import screen_recording_storage

            if expired_only:
                stats = screen_recording_storage.cleanup_expired(dry_run=self.dry_run)
                total = sum(stats.values())
                self.stats.files_deleted += total

                action = "将清理" if self.dry_run else "已清理"
                print(f"  ✅ {action} {total} 个过期录制")
                for item_type, count in stats.items():
                    if count > 0:
                        print(f"     - {item_type}: {count}")
            else:
                # 清理所有录制
                base_dir = self.settings.SCREEN_RECORDINGS_DIR

                if not os.path.exists(base_dir):
                    print("  ℹ️  录制目录不存在")
                    return True

                # 统计文件数量
                video_count = 0
                frame_count = 0
                total_size = 0

                for root, dirs, files in os.walk(base_dir):
                    for file in files:
                        if file.endswith((".mp4", ".mov", ".avi", ".mkv")):
                            video_count += 1
                        elif file.endswith((".png", ".jpg", ".jpeg")):
                            frame_count += 1
                        filepath = os.path.join(root, file)
                        try:
                            total_size += os.path.getsize(filepath)
                        except:
                            pass

                total_files = video_count + frame_count

                if total_files == 0:
                    print("  ℹ️  没有录制需要清理")
                    return True

                if not self._confirm(f"删除 {video_count} 个视频和 {frame_count} 个帧 ({total_size / (1024 * 1024):.2f} MB)?"):
                    print("  ⏭️  已跳过")
                    return True

                if not self.dry_run:
                    shutil.rmtree(base_dir, ignore_errors=True)
                    os.makedirs(base_dir, exist_ok=True)
                    os.makedirs(
                        os.path.join(base_dir, "frames"),
                        exist_ok=True
                    )

                self.stats.files_deleted += total_files
                self.stats.storage_freed_mb += total_size / (1024 * 1024)

                action = "将删除" if self.dry_run else "已删除"
                print(f"  ✅ {action} {video_count} 个视频，{frame_count} 个帧")

            return True

        except Exception as e:
            logger.error(f"  ❌ 录制清理失败：{e}")
            self.stats.errors.append(f"录制: {e}")
            return False

    def cleanup_knowledge_base(self) -> bool:
        """
        清理文件系统知识库。

        知识库存储架构：
        - 语义知识（概念）：以 Concept 节点形式存储在 Neo4j 中（使用 --memory 清理）
        - 基于文件的知识：存储在 ~/.evoloop/library/ 中（此方法清理这些文件）

        目录：
        - ~/.evoloop/library/ - 全局知识库文件（markdown、技能定义）
        """
        print("\n📚 知识库清理")
        print("-" * 40)

        try:
            kb_dir = self.settings.LIBRARY_ROOT

            if not os.path.exists(kb_dir):
                print("  ℹ️  知识库目录不存在")
                return True

            # 统计文件数量
            file_count = 0
            total_size = 0
            for root, dirs, files in os.walk(kb_dir):
                for file in files:
                    file_count += 1
                    filepath = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(filepath)
                    except:
                        pass

            dir_count = sum(1 for _, dirs, _ in os.walk(kb_dir) for d in dirs)

            if file_count == 0:
                print("  ℹ️  没有知识库文件需要清理")
                return True

            if not self._confirm(f"删除 {file_count} 个知识库文件 ({total_size / (1024 * 1024):.2f} MB)?"):
                print("  ⏭️  已跳过")
                return True

            if not self.dry_run:
                shutil.rmtree(kb_dir, ignore_errors=True)
                os.makedirs(kb_dir, exist_ok=True)

            self.stats.files_deleted += file_count
            self.stats.directories_removed += dir_count
            self.stats.storage_freed_mb += total_size / (1024 * 1024)

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {file_count} 个知识库文件")
            return True

        except Exception as e:
            logger.error(f"  ❌ 知识库清理失败：{e}")
            self.stats.errors.append(f"知识库: {e}")
            return False

    def cleanup_brain_memory(self) -> bool:
        """
        清理大脑记忆目录。

        目录：
        - ~/.evoloop/memory/ - 大脑记忆文件
        """
        print("\n🧠 大脑记忆清理")
        print("-" * 40)

        try:
            brain_dir = self.settings.BRAIN_MEMORY_ROOT

            if not os.path.exists(brain_dir):
                print("  ℹ️  大脑记忆目录不存在")
                return True

            # 统计文件数量
            file_count = 0
            total_size = 0
            for root, dirs, files in os.walk(brain_dir):
                for file in files:
                    file_count += 1
                    filepath = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(filepath)
                    except:
                        pass

            if file_count == 0:
                print("  ℹ️  没有大脑记忆文件需要清理")
                return True

            if not self._confirm(f"删除 {file_count} 个大脑记忆文件 ({total_size / (1024 * 1024):.2f} MB)?"):
                print("  ⏭️  已跳过")
                return True

            if not self.dry_run:
                shutil.rmtree(brain_dir, ignore_errors=True)
                os.makedirs(brain_dir, exist_ok=True)

            self.stats.files_deleted += file_count
            self.stats.storage_freed_mb += total_size / (1024 * 1024)

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {file_count} 个大脑记忆文件")
            return True

        except Exception as e:
            logger.error(f"  ❌ 大脑记忆清理失败：{e}")
            self.stats.errors.append(f"大脑记忆: {e}")
            return False

    def cleanup_keychain(self) -> bool:
        """
        清理 macOS Keychain / 系统密钥库中存储的凭据。
        包括：cloud_token, device_key, member_id
        """
        print("\n🔑 KEYCHAIN 凭据清理")
        print("-" * 40)

        try:
            import keyring

            service = "EvoLoop"
            accounts = ["cloud_token", "device_key", "member_id"]
            deleted = []
            errors = []

            for account in accounts:
                try:
                    # 检查是否存在
                    existing = keyring.get_password(service, account)
                    if existing:
                        if not self.dry_run:
                            keyring.delete_password(service, account)
                        deleted.append(account)
                        logger.info(f"  {account}: {'将删除' if self.dry_run else '已删除'}")
                    else:
                        logger.info(f"  {account}: 不存在")
                except keyring.errors.PasswordDeleteError:
                    # 已经删除或不存在
                    pass
                except Exception as e:
                    errors.append(f"{account}: {e}")
                    logger.warning(f"  {account}: 删除失败 - {e}")

            action = "将删除" if self.dry_run else "已删除"
            print(f"  ✅ {action} {len(deleted)} 个凭据项")
            if deleted:
                for item in deleted:
                    print(f"     - {item}")

            return True

        except ImportError:
            logger.warning("  ⚠️  keyring 库不可用")
            return False
        except Exception as e:
            logger.error(f"  ❌ Keychain 清理失败：{e}")
            self.stats.errors.append(f"Keychain: {e}")
            return False

    async def cleanup_conversations(self, days: int | None = None) -> bool:
        """
        清理对话及相关数据。

        涉及表（共10张，按依赖顺序清理）：
        1. checkpoint_writes - Checkpoint 写入记录（依赖 checkpoints）
        2. checkpoint_blobs - Checkpoint 二进制数据
        3. checkpoints - Checkpoint 主表（依赖 conversations）
        4. message_references - 消息引用（依赖 messages）
        5. messages - 消息记录（依赖 conversations）
        6. human_requests - 人工请求（依赖 conversations）
        7. file_operations - 文件操作记录（依赖 conversations）
        8. plan_steps - 计划步骤（依赖 plans）
        9. plans - 任务计划（依赖 conversations，外键+级联）
        10. conversations - 对话主表

        注意：trace_events 在技能清理中处理，todos 需单独清理，checkpoint_migrations 保留

        Args:
            days: 只清理 N 天前的对话，None 表示清理所有
        """
        print("\n💬 对话清理")
        print("-" * 40)

        try:
            from sqlalchemy import text
            from app.infrastructure.database.sql.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                # 统计各表数据（注意：trace_events 在技能清理中，todos 需单独清理，checkpoint_migrations 保留）
                tables_info = [
                    ("conversations", "id IS NOT NULL"),
                    ("checkpoints", "1=1"),
                    ("checkpoint_writes", "1=1"),
                    ("checkpoint_blobs", "1=1"),
                    ("messages", "1=1"),
                    ("message_references", "1=1"),
                    ("human_requests", "1=1"),
                    ("file_operations", "1=1"),
                    ("plans", "1=1"),
                    ("plan_steps", "1=1"),
                ]

                stats_before = {}
                for table, condition in tables_info:
                    try:
                        result = await session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {condition}"))
                        stats_before[table] = result.scalar() or 0
                    except Exception:
                        stats_before[table] = 0

                total_related = sum(stats_before.values()) - stats_before.get("conversations", 0)
                conv_count = stats_before.get("conversations", 0)

                if conv_count == 0:
                    print("  ℹ️  没有对话数据需要清理")
                    return True

                print(f"  发现 {conv_count} 个对话，关联 {total_related} 条记录")
                for table, count in stats_before.items():
                    if count > 0:
                        print(f"    - {table}: {count}")

                if self.dry_run:
                    print(f"  🔍 试运行：将清理 {conv_count} 个对话及其关联数据")
                    return True

                if not self._confirm(f"删除 {conv_count} 个对话及所有关联数据?"):
                    print("  ⏭️  已跳过")
                    return False

                # 构建时间条件
                time_condition = ""
                if days is not None:
                    time_condition = f"AND created_at < NOW() - INTERVAL '{days} days'"
                    print(f"  📅 只清理 {days} 天前的对话")

                deleted_rows = 0

                # 1. 清理 checkpoint 相关表（按依赖顺序：writes -> blobs -> checkpoints）
                # 1a. 清理 checkpoint_writes
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM checkpoint_writes
                        WHERE thread_id IN (
                            SELECT id FROM conversations WHERE 1=1 {time_condition}
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    if count > 0:
                        print(f"  ✅ 已删除 {count} 条 checkpoint 写入记录")
                except Exception as e:
                    logger.warning(f"  清理 checkpoint_writes 失败：{e}")

                # 1b. 清理 checkpoint_blobs
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM checkpoint_blobs
                        WHERE thread_id IN (
                            SELECT id FROM conversations WHERE 1=1 {time_condition}
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    if count > 0:
                        print(f"  ✅ 已删除 {count} 条 checkpoint 二进制数据")
                except Exception as e:
                    logger.warning(f"  清理 checkpoint_blobs 失败：{e}")

                # 1c. 清理 checkpoints 主表
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM checkpoints
                        WHERE thread_id IN (
                            SELECT id FROM conversations WHERE 1=1 {time_condition}
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    if count > 0:
                        print(f"  ✅ 已删除 {count} 个 checkpoint")
                except Exception as e:
                    logger.warning(f"  清理 checkpoints 失败：{e}")

                # 2. 清理 message_references（通过 message_id 关联）
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM message_references
                        WHERE message_id IN (
                            SELECT id FROM messages
                            WHERE thread_id IN (
                                SELECT id FROM conversations WHERE 1=1 {time_condition}
                            )
                        )
                    """))
                    deleted_rows += result.rowcount or 0
                except Exception as e:
                    logger.warning(f"  清理 message_references 失败：{e}")

                # 2. 清理 messages
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM messages
                        WHERE thread_id IN (
                            SELECT id FROM conversations WHERE 1=1 {time_condition}
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    print(f"  ✅ 已删除 {count} 条消息")
                except Exception as e:
                    logger.warning(f"  清理 messages 失败：{e}")

                # 3. 清理 human_requests
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM human_requests
                        WHERE thread_id IN (
                            SELECT id FROM conversations WHERE 1=1 {time_condition}
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    if count > 0:
                        print(f"  ✅ 已删除 {count} 条人工请求")
                except Exception as e:
                    logger.warning(f"  清理 human_requests 失败：{e}")

                # 4. 清理 file_operations
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM file_operations
                        WHERE thread_id IN (
                            SELECT id FROM conversations WHERE 1=1 {time_condition}
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    if count > 0:
                        print(f"  ✅ 已删除 {count} 条文件操作记录")
                except Exception as e:
                    logger.warning(f"  清理 file_operations 失败：{e}")

                # 5. 清理 plan_steps（plans 有级联删除，但先手动清理更可控）
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM plan_steps
                        WHERE plan_id IN (
                            SELECT id FROM plans WHERE thread_id IN (
                                SELECT id FROM conversations WHERE 1=1 {time_condition}
                            )
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    if count > 0:
                        print(f"  ✅ 已删除 {count} 条计划步骤")
                except Exception as e:
                    logger.warning(f"  清理 plan_steps 失败：{e}")

                # 6. 清理 plans
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM plans
                        WHERE thread_id IN (
                            SELECT id FROM conversations WHERE 1=1 {time_condition}
                        )
                    """))
                    count = result.rowcount or 0
                    deleted_rows += count
                    if count > 0:
                        print(f"  ✅ 已删除 {count} 个计划")
                except Exception as e:
                    logger.warning(f"  清理 plans 失败：{e}")

                # 7. 最后清理 conversations 主表
                try:
                    result = await session.execute(text(f"""
                        DELETE FROM conversations
                        WHERE 1=1 {time_condition}
                    """))
                    conv_deleted = result.rowcount or 0
                    deleted_rows += conv_deleted
                    print(f"  ✅ 已删除 {conv_deleted} 个对话")
                except Exception as e:
                    logger.error(f"  清理 conversations 失败：{e}")
                    self.stats.errors.append(f"conversations: {e}")

                await session.commit()

                self.stats.postgres_rows_deleted += deleted_rows
                action = "将删除" if self.dry_run else "已删除"
                print(f"  ✅ {action} {deleted_rows} 条对话相关记录")
                return True

        except ImportError as e:
            logger.warning(f"  ⚠️  PostgreSQL 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ 对话清理失败：{e}")
            self.stats.errors.append(f"对话: {e}")
            return False

    async def cleanup_todos(self) -> bool:
        """
        清理待办事项表。

        表：
        - todos - 待办事项
        """
        print("\n📋 待办事项清理")
        print("-" * 40)

        try:
            from sqlalchemy import text
            from app.infrastructure.database.sql.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                # 统计待办事项
                result = await session.execute(text("SELECT COUNT(*) FROM todos"))
                count = result.scalar() or 0

                if self.dry_run:
                    print(f"  🔍 发现 {count} 条待办事项")
                    return True

                if count == 0:
                    print("  ℹ️  没有待办事项需要清理")
                    return True

                if not self._confirm(f"删除 {count} 条待办事项?"):
                    print("  ⏭️  已跳过")
                    return False

                result = await session.execute(text("TRUNCATE TABLE todos CASCADE"))
                await session.commit()

                self.stats.postgres_rows_deleted += count
                print(f"  ✅ 已删除 {count} 条待办事项")
                return True

        except ImportError as e:
            logger.warning(f"  ⚠️  PostgreSQL 不可用：{e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ 待办事项清理失败：{e}")
            self.stats.errors.append(f"待办事项: {e}")
            return False

    async def run_all(self, args):
        """根据命令行参数运行清理。"""
        print("=" * 60)
        print("🧹 EVOLOOP 系统清理")
        print("=" * 60)

        if self.dry_run:
            print("\n⚠️  试运行模式 - 不会进行实际更改\n")

        if args.all or args.keychain:
            self.cleanup_keychain()

        if args.all or args.redis:
            await self.cleanup_redis()

        if args.all or args.neo4j:
            await self.cleanup_neo4j_index(keep_apps=args.keep_apps)

        if args.all or args.memory:
            await self.cleanup_neo4j_memory()

        if args.all or args.skills:
            await self.cleanup_skills()

        if args.all or args.index:
            await self.cleanup_postgres_index()

        if args.all or args.messages:
            await self.cleanup_postgres_messages()

        if args.all or args.jobs:
            await self.cleanup_postgres_jobs()

        if args.all or args.screenshots:
            self.cleanup_screenshots(expired_only=args.expired_only)

        if args.all or args.recordings:
            self.cleanup_recordings(expired_only=args.expired_only)

        if args.all or args.knowledge:
            self.cleanup_knowledge_base()

        if args.all or args.brain:
            self.cleanup_brain_memory()

        if args.all or args.todos:
            await self.cleanup_todos()

        if args.all or args.conversations:
            await self.cleanup_conversations(days=args.conversation_days)

        # 打印摘要
        self.stats.print_summary()


async def main():
    parser = argparse.ArgumentParser(
        description="EvoLoop 系统清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 预览将被删除的内容
  python cleanup_system.py --dry-run --all

  # 仅清理 Redis 和技能
  python cleanup_system.py --redis --skills

  # 仅清理记忆（概念、执行记录、偏好设置）
  python cleanup_system.py --memory

  # 清理文件索引但保留 Atlas 应用数据
  python cleanup_system.py --neo4j --keep-apps

  # 清理所有内容并确认
  python cleanup_system.py --all --confirm

  # 仅清理过期数据
  python cleanup_system.py --expired-only --screenshots --recordings

  # 清理知识库文件（概念使用 --memory）
  python cleanup_system.py --knowledge

  # 清理 Keychain 登录凭据（注销登录）
  python cleanup_system.py --keychain
        """,
    )

    # 组件选择
    parser.add_argument(
        "--all", action="store_true", help="清理所有组件（谨慎使用！）"
    )
    parser.add_argument(
        "--redis", action="store_true", help="清理 Redis 缓存"
    )
    parser.add_argument(
        "--neo4j", action="store_true", help="清理 Neo4j 文件索引（文件、目录、代码实体、代码块、应用、状态）"
    )
    parser.add_argument(
        "--memory", action="store_true", help="清理 Neo4j 记忆节点（概念、执行记录、偏好、用户）"
    )
    parser.add_argument(
        "--skills", action="store_true", help="清理技能（数据库表和 ~/.evoloop/skills/ 文件）"
    )
    parser.add_argument(
        "--index", action="store_true", help="清理 PostgreSQL 文件索引表"
    )
    parser.add_argument(
        "--messages", action="store_true", help="清理 PostgreSQL 消息表"
    )
    parser.add_argument(
        "--jobs", action="store_true", help="清理 PostgreSQL 任务队列"
    )
    parser.add_argument(
        "--screenshots", action="store_true", help="清理截图存储"
    )
    parser.add_argument(
        "--recordings", action="store_true", help="清理屏幕录制存储"
    )
    parser.add_argument(
        "--knowledge", action="store_true", help="清理文件系统知识库"
    )
    parser.add_argument(
        "--brain", action="store_true", help="清理大脑记忆文件"
    )
    parser.add_argument(
        "--keychain", action="store_true", help="清理 Keychain 中存储的登录凭据 (cloud_token, device_key, member_id)"
    )
    parser.add_argument(
        "--todos", action="store_true", help="清理待办事项表"
    )
    parser.add_argument(
        "--conversations", action="store_true", help="清理对话及关联数据（消息、计划、文件操作等7张表）"
    )
    parser.add_argument(
        "--conversation-days", type=int, default=None, help="只清理 N 天前的对话（与 --conversations 配合使用）"
    )

    # 选项
    parser.add_argument(
        "--dry-run", action="store_true", help="预览将被删除的内容而不实际执行"
    )
    parser.add_argument(
        "--confirm", action="store_true", help="删除前请求确认"
    )
    parser.add_argument(
        "--expired-only", action="store_true", help="仅清理过期数据（截图/录制）"
    )
    parser.add_argument(
        "--keep-apps", action="store_true", help="在 Neo4j 中保留 Atlas 应用数据"
    )

    args = parser.parse_args()

    # 如果未指定组件，显示帮助
    if not any([
        args.all, args.redis, args.neo4j, args.memory, args.skills, args.index,
        args.messages, args.jobs, args.screenshots, args.recordings,
        args.knowledge, args.brain, args.keychain, args.todos, args.conversations
    ]):
        parser.print_help()
        return

    # 警告 --all
    if args.all and not args.dry_run:
        print("⚠️  警告：您即将删除所有 EvoLoop 数据！")
        print("这将包括：")
        print("  - Keychain 登录凭据 (cloud_token, device_key, member_id)")
        print("  - Redis 缓存")
        print("  - Neo4j 文件索引和记忆（概念、执行记录等）")
        print("  - PostgreSQL 技能、索引、消息、任务")
        print("  - 截图和屏幕录制")
        print("  - 知识库和大脑记忆文件")
        print()
        confirm = input("输入 'DELETE' 确认：")
        if confirm != "DELETE":
            print("已中止。")
            return

    # 运行清理
    manager = CleanupManager(dry_run=args.dry_run, confirm=args.confirm)
    await manager.run_all(args)


if __name__ == "__main__":
    asyncio.run(main())
