"""
Knowledge Base Auto-Maintenance Service - 知识库自动整理系统

自动执行以下整理任务：
1. 重复文档检测与合并
2. 低质量内容识别与标记
3. 冷门文档归档
4. 热点内容优化建议
5. 知识图谱自动构建

使用方式：
    from app.domain.knowledge.services.auto_maintenance import get_maintenance_service

    # 手动触发整理
    service = get_maintenance_service()
    report = await service.run_maintenance()

    # 定期自动整理（由调度器调用）
    await service.run_scheduled_maintenance()
"""

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.domain.knowledge.models import MarkdownDocument
from app.domain.knowledge.services.citations import get_citation_tracker
from app.domain.knowledge.services.deduplication import DeduplicationService
from app.domain.knowledge.services.search import get_fts_service, IndexDocumentRequest
from app.domain.knowledge.services.store import KnowledgeStoreService
from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


class MaintenanceConfig(BaseModel):
    """Configuration for auto-maintenance tasks."""
    enable_auto_merge: bool = True
    enable_auto_archive: bool = True
    similarity_threshold: float = 0.85
    cold_doc_days: int = 90
    min_quality_score: float = 0.3


class UsageDocInfo(BaseModel, LegacyDictMixin):
    """Usage information for a single document."""
    path: str
    citations: int
    last_accessed: Optional[str] = None
    unique_sessions: Optional[int] = None


class UsageAnalysisResult(BaseModel, LegacyDictMixin):
    """Result of analyzing document usage patterns."""
    hot_docs: list[UsageDocInfo] = Field(default_factory=list)
    cold_docs: list[UsageDocInfo] = Field(default_factory=list)
    total_analyzed: int = 0


class OptimizationSuggestion(BaseModel, LegacyDictMixin):
    """Optimization suggestion based on usage analysis."""
    type: str
    reason: str
    priority: str = "medium"
    path: Optional[str] = None
    count: Optional[int] = None


class MaintenanceReport(BaseModel, LegacyDictMixin):
    """知识库整理报告"""
    timestamp: datetime = Field(default_factory=datetime.now)
    duration_seconds: float = 0.0
    tasks_completed: list[str] = Field(default_factory=list)
    tasks_failed: list[str] = Field(default_factory=list)

    # 重复文档处理
    duplicates_found: int = 0
    duplicates_merged: int = 0
    duplicates_deleted: int = 0

    # 低质量内容
    low_quality_found: int = 0
    low_quality_archived: int = 0

    # 冷门内容
    cold_docs_found: int = 0
    cold_docs_archived: int = 0

    # 热点优化
    hot_docs_found: int = 0
    hot_optimization_suggestions: list[OptimizationSuggestion] = Field(default_factory=list)

    # 知识图谱
    entities_extracted: int = 0
    relations_created: int = 0

    def to_dict(self) -> dict:
        """Backward compatibility for existing code calling to_dict manually."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "duplicates": {
                "found": self.duplicates_found,
                "merged": self.duplicates_merged,
                "deleted": self.duplicates_deleted,
            },
            "low_quality": {
                "found": self.low_quality_found,
                "archived": self.low_quality_archived,
            },
            "cold_content": {
                "found": self.cold_docs_found,
                "archived": self.cold_docs_archived,
            },
            "hot_content": {
                "found": self.hot_docs_found,
                "suggestions": [s.model_dump() for s in self.hot_optimization_suggestions],
            },
            "knowledge_graph": {
                "entities": self.entities_extracted,
                "relations": self.relations_created,
            },
        }


class DocumentQuality(BaseModel, LegacyDictMixin):
    """文档质量评估"""
    path: str
    score: float  # 0.0 - 1.0
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class UsageAnalyzer:
    """基于使用情况的文档分析器"""

    def __init__(self):
        self.citation_tracker = get_citation_tracker()

    async def analyze_usage_patterns(self, days: int = 30) -> UsageAnalysisResult:
        """
        分析文档使用模式

        Returns:
            {
                "hot_docs": [...],      # 高频使用文档
                "cold_docs": [...],     # 长期未使用文档
                "trending_docs": [...], # 近期上升趋势文档
                "orphaned_docs": [...], # 孤立文档（无引用）
            }
        """
        await self.citation_tracker.initialize()

        # 获取所有引用统计
        popular = await self.citation_tracker.get_most_cited(limit=1000)

        hot_docs: list[UsageDocInfo] = []
        cold_docs: list[UsageDocInfo] = []
        now = datetime.now()

        for doc in popular[:50]:  # 前50热门
            stats = await self.citation_tracker.get_document_stats(doc.doc_path)
            if not stats:
                continue

            last_accessed = stats.last_accessed
            if last_accessed:
                days_since = (now - datetime.fromisoformat(last_accessed)).days

                if days_since < 7:  # 一周内访问过
                    hot_docs.append(UsageDocInfo(
                        path=doc.doc_path,
                        citations=stats.total_citations,
                        unique_sessions=stats.unique_sessions,
                        last_accessed=last_accessed,
                    ))

        # 冷门文档：引用次数少且最近未访问
        cutoff_date = now - timedelta(days=days)
        for doc in popular[100:]:  # 100名以后
            stats = await self.citation_tracker.get_document_stats(doc.doc_path)
            if not stats:
                continue

            last_accessed = stats.last_accessed
            if last_accessed:
                last_date = datetime.fromisoformat(last_accessed)
                if last_date < cutoff_date and stats.total_citations < 3:
                    cold_docs.append(UsageDocInfo(
                        path=doc.doc_path,
                        citations=stats.total_citations,
                        last_accessed=last_accessed,
                    ))

        return UsageAnalysisResult(
            hot_docs=hot_docs,
            cold_docs=cold_docs,
            total_analyzed=len(popular),
        )

    async def suggest_optimizations(self) -> list[OptimizationSuggestion]:
        """基于使用数据给出优化建议"""
        suggestions = []
        patterns = await self.analyze_usage_patterns()

        # 建议1：为热门文档创建摘要
        for doc in patterns.hot_docs[:10]:
            suggestions.append(OptimizationSuggestion(
                type="create_summary",
                path=doc.path,
                reason=f"高频使用 ({doc.citations} 次引用)，建议创建摘要版本",
                priority="high",
            ))

        # 建议2：归档冷门文档
        if len(patterns.cold_docs) > 10:
            suggestions.append(OptimizationSuggestion(
                type="archive_cold",
                count=len(patterns.cold_docs),
                reason=f"发现 {len(patterns.cold_docs)} 个长期未使用文档",
                priority="medium",
            ))

        # 建议3：检查孤立的热门文档
        hot_paths = {d["path"] for d in patterns["hot_docs"]}
        # 如果热门文档之间没有关联，建议建立链接

        return suggestions


class QualityChecker:
    """文档质量检查器"""

    MIN_CONTENT_LENGTH = 100  # 最少字符数
    MIN_WORD_COUNT = 20       # 最少词数
    MAX_DUPLICATE_RATIO = 0.7 # 最大重复内容比例

    def __init__(self, store: Optional[KnowledgeStoreService] = None):
        self.store = store or KnowledgeStoreService()

    async def check_quality(self, path: str) -> DocumentQuality:
        """检查单个文档质量"""
        issues = []
        suggestions = []

        try:
            result = self.store.read_document(path)
            content = result.get("content", "")

            # 检查1：内容长度
            if len(content) < self.MIN_CONTENT_LENGTH:
                issues.append("内容过短")
                suggestions.append("补充更多内容或考虑删除")

            # 检查2：词数
            word_count = len(content.split())
            if word_count < self.MIN_WORD_COUNT:
                issues.append("词汇量不足")

            # 检查3：格式问题
            if content.count("#") == 0:
                suggestions.append("添加标题结构提高可读性")

            # 检查4：重复内容
            lines = content.split("\n")
            unique_lines = set(lines)
            if len(lines) > 0:
                duplicate_ratio = 1 - (len(unique_lines) / len(lines))
                if duplicate_ratio > self.MAX_DUPLICATE_RATIO:
                    issues.append(f"重复内容过多 ({duplicate_ratio:.0%})")

            # 检查5：链接有效性（简化检查）
            import re
            links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
            broken_links = []
            for text, link in links:
                if link.startswith("http"):
                    # 暂不检查外部链接
                    pass
                elif not link.startswith("#"):
                    # 检查内部链接
                    try:
                        self.store.read_document(link)
                    except:
                        broken_links.append(link)

            if broken_links:
                issues.append(f"发现 {len(broken_links)} 个损坏的内部链接")
                suggestions.append("修复或移除损坏的链接")

            # 计算质量分数
            score = 1.0

            # 根据严重程度扣分
            for issue in issues:
                if "过短" in issue or "不足" in issue:
                    score -= 0.4  # 严重问题
                elif "重复" in issue:
                    score -= 0.3
                elif "链接" in issue:
                    score -= 0.2
                else:
                    score -= 0.1

            score -= len(broken_links) * 0.05
            score -= len(suggestions) * 0.05  # 改进建议也略微扣分
            score = max(0.0, score)

            return DocumentQuality(
                path=path,
                score=score,
                issues=issues,
                suggestions=suggestions,
            )

        except Exception as e:
            return DocumentQuality(
                path=path,
                score=0.0,
                issues=[f"无法读取文档: {e}"],
                suggestions=["检查文档完整性"],
            )

    async def scan_collection(self, collection: Optional[str] = None) -> list[DocumentQuality]:
        """扫描整个集合的质量"""
        documents = self.store.list_documents(collection)
        results = []

        for doc in documents:
            quality = await self.check_quality(doc.path)
            results.append(quality)

        # 按质量分数排序
        results.sort(key=lambda x: x.score)
        return results


class AutoMaintenanceService:
    """
    知识库自动整理服务

    执行策略：
    1. 每小时：轻度整理（检测重复、质量检查）
    2. 每天：中度整理（合并重复、归档冷门）
    3. 每周：深度整理（知识图谱构建、全面优化）
    """

    def __init__(self):
        self.store = KnowledgeStoreService()
        self.dedup_service = DeduplicationService(self.store)
        self.usage_analyzer = UsageAnalyzer()
        self.quality_checker = QualityChecker(self.store)
        self.fts_service = None  # 延迟初始化

        # 配置
        self.config = MaintenanceConfig()

    async def _get_fts(self):
        """延迟初始化 FTS 服务"""
        if self.fts_service is None:
            self.fts_service = get_fts_service()
        return self.fts_service

    async def run_maintenance(
        self,
        collection: Optional[str] = None,
        dry_run: bool = True
    ) -> MaintenanceReport:
        """
        执行完整的维护任务

        Args:
            collection: 指定集合，None=所有
            dry_run: 如果为 True，只报告不执行修改
        """
        start_time = datetime.now()
        report = MaintenanceReport(
            timestamp=start_time,
            duration_seconds=0,
            tasks_completed=[],
            tasks_failed=[],
        )

        logger.info(f"🔧 开始知识库自动整理 {'[模拟模式]' if dry_run else ''}")

        # 任务1：重复文档检测与处理
        try:
            await self._task_deduplication(report, collection, dry_run)
            report.tasks_completed.append("deduplication")
        except Exception as e:
            logger.error(f"重复文档处理失败: {e}")
            report.tasks_failed.append(f"deduplication: {e}")

        # 任务2：质量检查
        try:
            await self._task_quality_check(report, collection, dry_run)
            report.tasks_completed.append("quality_check")
        except Exception as e:
            logger.error(f"质量检查失败: {e}")
            report.tasks_failed.append(f"quality_check: {e}")

        # 任务3：使用分析
        try:
            await self._task_usage_analysis(report, dry_run)
            report.tasks_completed.append("usage_analysis")
        except Exception as e:
            logger.error(f"使用分析失败: {e}")
            report.tasks_failed.append(f"usage_analysis: {e}")

        # 任务4：冷门内容归档
        try:
            await self._task_archive_cold(report, collection, dry_run)
            report.tasks_completed.append("archive_cold")
        except Exception as e:
            logger.error(f"冷门归档失败: {e}")
            report.tasks_failed.append(f"archive_cold: {e}")

        # 任务5：热点优化建议
        try:
            await self._task_hot_optimization(report)
            report.tasks_completed.append("hot_optimization")
        except Exception as e:
            logger.error(f"热点优化失败: {e}")
            report.tasks_failed.append(f"hot_optimization: {e}")

        # 任务6：索引优化
        try:
            await self._task_index_optimization(report, collection)
            report.tasks_completed.append("index_optimization")
        except Exception as e:
            logger.error(f"索引优化失败: {e}")
            report.tasks_failed.append(f"index_optimization: {e}")

        # 计算耗时
        report.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(f"✅ 知识库整理完成，耗时 {report.duration_seconds:.1f}s")
        logger.info(f"   完成任务: {len(report.tasks_completed)}")
        logger.info(f"   失败任务: {len(report.tasks_failed)}")

        return report

    async def _task_deduplication(
        self,
        report: MaintenanceReport,
        collection: Optional[str],
        dry_run: bool
    ):
        """任务：重复文档处理"""
        logger.info("📋 检测重复文档...")

        dedup_report = await self.dedup_service.analyze_project(collection)
        report.duplicates_found = len(dedup_report.exact_duplicates)

        # 处理精确重复
        if dedup_report.exact_duplicates and not dry_run:
            # 保留每个重复组中的第一个，删除其余的
            to_delete = set()
            for pair in dedup_report.exact_duplicates:
                to_delete.add(pair[1])  # 删除第二个

            for path in to_delete:
                try:
                    self.store.delete_document(path)
                    report.duplicates_deleted += 1
                except Exception as e:
                    logger.warning(f"删除重复文档失败 {path}: {e}")

        # 处理相似文档
        if dedup_report.potential_merges and self.config.enable_auto_merge and not dry_run:
            for merge_suggestion in dedup_report.potential_merges[:3]:  # 限制合并数量
                docs = merge_suggestion.documents
                if len(docs) >= 2:
                    result = await self.dedup_service.merge_documents(
                        docs,
                        strategy="deduplicate"
                    )
                    if result.success:
                        report.duplicates_merged += 1

    async def _task_quality_check(
        self,
        report: MaintenanceReport,
        collection: Optional[str],
        dry_run: bool
    ):
        """任务：质量检查"""
        logger.info("🔍 检查文档质量...")

        quality_results = await self.quality_checker.scan_collection(collection)

        low_quality = [q for q in quality_results if q.score < self.config.min_quality_score]
        report.low_quality_found = len(low_quality)

        if not dry_run:
            # 标记低质量文档（移动到低质量集合）
            for q in low_quality[:10]:  # 限制处理数量
                try:
                    # 读取文档
                    result = self.store.read_document(q.path)
                    content = result.content

                    # 添加质量标记
                    from app.domain.knowledge.models import MarkdownDocument
                    doc = MarkdownDocument(
                        content=content,
                        source=result.get("source", "unknown"),
                        mime_type="text/markdown",
                        metadata={
                            **result.get("metadata", {}),
                            "quality_score": q.score,
                            "quality_issues": q.issues,
                            "quality_checked_at": datetime.now().isoformat(),
                        }
                    )

                    # 保存到低质量集合
                    self.store.save_document(
                        doc,
                        collection="quality-review",
                        path=q.path.replace("/", "--")
                    )
                    report.low_quality_archived += 1

                except Exception as e:
                    logger.warning(f"归档低质量文档失败 {q.path}: {e}")

    async def _task_usage_analysis(
        self,
        report: MaintenanceReport,
        dry_run: bool
    ):
        """任务：使用分析"""
        logger.info("📊 分析使用情况...")

        patterns = await self.usage_analyzer.analyze_usage_patterns(days=30)

        report.hot_docs_found = len(patterns.get("hot_docs", []))
        report.cold_docs_found = len(patterns.get("cold_docs", []))

        # 生成优化建议
        suggestions = await self.usage_analyzer.suggest_optimizations()
        report.hot_optimization_suggestions = suggestions

        # 记录分析结果到日志
        logger.info(f"   热门文档: {report.hot_docs_found}")
        logger.info(f"   冷门文档: {report.cold_docs_found}")

    async def _task_archive_cold(
        self,
        report: MaintenanceReport,
        collection: Optional[str],
        dry_run: bool
    ):
        """任务：归档冷门内容"""
        if not self.config.enable_auto_archive:
            return

        logger.info("📦 归档冷门文档...")

        patterns = await self.usage_analyzer.analyze_usage_patterns(
            days=self.config.cold_doc_days
        )

        cold_docs = patterns.get("cold_docs", [])

        if not dry_run and cold_docs:
            for doc_info in cold_docs[:20]:  # 限制处理数量
                try:
                    path = doc_info.path
                    # 移动到归档集合
                    result = self.store.read_document(path)
                    content = result.content

                    from app.domain.knowledge.models import MarkdownDocument
                    doc = MarkdownDocument(
                        content=content,
                        source=result.get("source", "unknown"),
                        mime_type="text/markdown",
                        metadata={
                            **result.get("metadata", {}),
                            "archived_at": datetime.now().isoformat(),
                            "archive_reason": "cold_content",
                            "last_citations": doc_info.get("citations", 0),
                        }
                    )

                    # 保存到归档
                    self.store.save_document(
                        doc,
                        collection="archived",
                        path=path.replace("/", "--")
                    )

                    # 删除原位置
                    self.store.delete_document(path)
                    report.cold_docs_archived += 1

                except Exception as e:
                    logger.warning(f"归档冷门文档失败: {e}")

    async def _task_hot_optimization(self, report: MaintenanceReport):
        """任务：热点优化"""
        logger.info("🔥 分析热点优化机会...")

        suggestions = report.hot_optimization_suggestions

        for suggestion in suggestions:
            logger.info(f"   💡 {suggestion.type}: {suggestion.reason}")

    async def _task_index_optimization(
        self,
        report: MaintenanceReport,
        collection: Optional[str]
    ):
        """任务：索引优化"""
        logger.info("🔎 优化搜索索引...")

        try:
            fts = await self._get_fts()

            # 重新索引所有文档
            documents = self.store.list_documents(collection)
            reindexed = 0

            for doc in documents:
                try:
                    result = self.store.read_document(doc.path)
                    content = result.content

                    await fts.index_document(
                        IndexDocumentRequest(
                            doc_id=doc.path,
                            path=doc.path,
                            title=doc.title,
                            content=content[:10000],  # 限制索引长度
                            collection=collection or "default"
                        )
                    )
                    reindexed += 1

                except Exception as e:
                    logger.warning(f"索引文档失败 {doc.path}: {e}")

            logger.info(f"   重新索引: {reindexed} 个文档")

        except Exception as e:
            logger.warning(f"索引优化失败: {e}")

    async def run_scheduled_maintenance(self):
        """由调度器调用的定期维护"""
        hour = datetime.now().hour

        if hour == 2:  # 凌晨2点：完整维护
            logger.info("🌙 执行夜间完整维护")
            return await self.run_maintenance(dry_run=False)
        elif hour % 6 == 0:  # 每6小时：轻度维护
            logger.info("⏰ 执行定期轻度维护")
            # 只做分析和报告，不修改
            return await self.run_maintenance(dry_run=True)
        else:
            return None  # 跳过


# 全局服务实例
_maintenance_service: Optional[AutoMaintenanceService] = None


def get_maintenance_service() -> AutoMaintenanceService:
    """获取维护服务单例"""
    global _maintenance_service
    if _maintenance_service is None:
        _maintenance_service = AutoMaintenanceService()
    return _maintenance_service


async def run_knowledge_maintenance(
    collection: Optional[str] = None,
    dry_run: bool = True
) -> dict:
    """
    便捷函数：运行知识库维护

    Usage:
        result = await run_knowledge_maintenance(dry_run=False)
        print(result["duplicates"]["found"])
    """
    service = get_maintenance_service()
    report = await service.run_maintenance(collection=collection, dry_run=dry_run)
    return report.to_dict()
