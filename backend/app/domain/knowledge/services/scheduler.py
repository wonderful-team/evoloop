"""
Knowledge Base Maintenance Scheduler - 知识库维护调度器

自动调度执行知识库整理任务：
- 每小时：轻度分析（检测问题，生成报告）
- 每天凌晨2点：中度整理（合并重复、标记低质量）
- 每周日凌晨3点：深度整理（全面优化、知识图谱构建）

使用方式：
    # 在应用启动时启动调度器
    from app.domain.knowledge.services.scheduler import start_scheduler, stop_scheduler

    await start_scheduler()

    # 应用关闭时
    await stop_scheduler()
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.domain.knowledge.services.auto_maintenance import get_maintenance_service

logger = logging.getLogger(__name__)


class MaintenanceScheduler:
    """
    维护任务调度器

    调度策略：
    - 轻度检查：每小时运行，只检测不修改
    - 中度整理：每天 02:00 运行，执行合并和归档
    - 深度整理：每周日 03:00 运行，全面优化
    """

    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.maintenance_service = get_maintenance_service()

        # 上次运行时间记录
        self.last_light_check: Optional[datetime] = None
        self.last_medium_maintenance: Optional[datetime] = None
        self.last_deep_maintenance: Optional[datetime] = None

        # 配置
        self.config = {
            "light_check_interval_hours": 1,
            "medium_maintenance_hour": 2,      # 每天 02:00
            "deep_maintenance_day": 6,          # 周日 (0=周一, 6=周日)
            "deep_maintenance_hour": 3,         # 03:00
            "enable_auto_fix": True,            # 是否自动修复问题
        }

    async def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("调度器已在运行")
            return

        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        logger.info("🔄 知识库维护调度器已启动")

    async def stop(self):
        """停止调度器"""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("🛑 知识库维护调度器已停止")

    async def _scheduler_loop(self):
        """调度器主循环"""
        while self.running:
            try:
                await self._check_and_run_tasks()
                # 每分钟检查一次
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器循环错误: {e}")
                await asyncio.sleep(60)

    async def _check_and_run_tasks(self):
        """检查并执行到期的任务"""
        now = datetime.now()

        # 任务1：轻度检查（每小时）
        if self._should_run_light_check(now):
            await self._run_light_check()

        # 任务2：中度整理（每天 02:00）
        if self._should_run_medium_maintenance(now):
            await self._run_medium_maintenance()

        # 任务3：深度整理（每周日 03:00）
        if self._should_run_deep_maintenance(now):
            await self._run_deep_maintenance()

    def _should_run_light_check(self, now: datetime) -> bool:
        """是否应该执行轻度检查"""
        if self.last_light_check is None:
            return True

        hours_since = (now - self.last_light_check).total_seconds() / 3600
        return hours_since >= self.config["light_check_interval_hours"]

    def _should_run_medium_maintenance(self, now: datetime) -> bool:
        """是否应该执行中度整理"""
        # 检查是否是目标时间（02:00）
        if now.hour != self.config["medium_maintenance_hour"]:
            return False

        if self.last_medium_maintenance is None:
            return True

        # 确保每天只运行一次
        return self.last_medium_maintenance.date() != now.date()

    def _should_run_deep_maintenance(self, now: datetime) -> bool:
        """是否应该执行深度整理"""
        # 检查是否是周日和目标时间
        if now.weekday() != self.config["deep_maintenance_day"]:
            return False

        if now.hour != self.config["deep_maintenance_hour"]:
            return False

        if self.last_deep_maintenance is None:
            return True

        # 确保每周只运行一次
        days_since = (now - self.last_deep_maintenance).days
        return days_since >= 7

    async def _run_light_check(self):
        """执行轻度检查"""
        logger.info("🔍 执行轻度检查...")
        self.last_light_check = datetime.now()

        try:
            # 轻度检查：dry_run=True，只检测不修改
            report = await self.maintenance_service.run_maintenance(dry_run=True)

            # 记录结果
            logger.info(f"   发现重复文档: {report.duplicates_found}")
            logger.info(f"   低质量文档: {report.low_quality_found}")
            logger.info(f"   冷门文档: {report.cold_docs_found}")

            # 如果有严重问题，发送警报
            if report.duplicates_found > 10:
                logger.warning(f"⚠️ 发现大量重复文档 ({report.duplicates_found})，建议执行中度整理")

        except Exception as e:
            logger.error(f"轻度检查失败: {e}")

    async def _run_medium_maintenance(self):
        """执行中度整理"""
        logger.info("🔧 执行中度整理...")
        self.last_medium_maintenance = datetime.now()

        try:
            # 中度整理：dry_run=False，执行修复
            dry_run = not self.config["enable_auto_fix"]
            report = await self.maintenance_service.run_maintenance(dry_run=dry_run)

            # 记录结果
            logger.info(f"✅ 中度整理完成")
            logger.info(f"   合并重复: {report.duplicates_merged}")
            logger.info(f"   删除重复: {report.duplicates_deleted}")
            logger.info(f"   归档冷门: {report.cold_docs_archived}")
            logger.info(f"   耗时: {report.duration_seconds:.1f}s")

            # 保存报告到文件
            await self._save_report(report, "medium")

        except Exception as e:
            logger.error(f"中度整理失败: {e}")

    async def _run_deep_maintenance(self):
        """执行深度整理"""
        logger.info("🚀 执行深度整理...")
        self.last_deep_maintenance = datetime.now()

        try:
            # 深度整理：包含额外的优化任务
            dry_run = not self.config["enable_auto_fix"]
            report = await self.maintenance_service.run_maintenance(dry_run=dry_run)

            logger.info(f"✅ 深度整理完成")
            logger.info(f"   实体提取: {report.entities_extracted}")
            logger.info(f"   关系创建: {report.relations_created}")
            logger.info(f"   优化建议: {len(report.hot_optimization_suggestions)}")

            # 保存报告
            await self._save_report(report, "deep")

            # 生成优化建议摘要
            if report.hot_optimization_suggestions:
                logger.info("💡 优化建议:")
                for suggestion in report.hot_optimization_suggestions[:5]:
                    logger.info(f"   - {suggestion['type']}: {suggestion['reason']}")

        except Exception as e:
            logger.error(f"深度整理失败: {e}")

    async def _save_report(self, report, report_type: str):
        """保存维护报告"""
        try:
            import json
            from pathlib import Path

            # 确保目录存在
            reports_dir = Path.home() / ".evoloop" / "knowledge" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            timestamp = report.timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"maintenance_{report_type}_{timestamp}.json"
            filepath = reports_dir / filename

            # 保存报告
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

            logger.info(f"   报告已保存: {filepath}")

        except Exception as e:
            logger.warning(f"保存报告失败: {e}")

    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            "running": self.running,
            "last_light_check": self.last_light_check.isoformat() if self.last_light_check else None,
            "last_medium_maintenance": self.last_medium_maintenance.isoformat() if self.last_medium_maintenance else None,
            "last_deep_maintenance": self.last_deep_maintenance.isoformat() if self.last_deep_maintenance else None,
            "config": self.config,
        }


# 全局调度器实例
_scheduler: Optional[MaintenanceScheduler] = None


async def start_scheduler() -> MaintenanceScheduler:
    """启动维护调度器"""
    global _scheduler
    if _scheduler is None:
        _scheduler = MaintenanceScheduler()

    await _scheduler.start()
    return _scheduler


async def stop_scheduler():
    """停止维护调度器"""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None


def get_scheduler() -> Optional[MaintenanceScheduler]:
    """获取调度器实例"""
    return _scheduler


async def run_manual_maintenance(
    collection: Optional[str] = None,
    dry_run: bool = False,
    level: str = "medium"
) -> dict:
    """
    手动运行维护任务

    Args:
        collection: 指定集合，None=所有
        dry_run: 是否只检测不修改
        level: 维护级别 (light, medium, deep)

    Returns:
        维护报告
    """
    service = get_maintenance_service()

    logger.info(f"🛠️ 手动运行 {level} 级别维护任务")

    if level == "light":
        # 轻度检查只运行分析任务
        report = await service.run_maintenance(collection=collection, dry_run=True, level=level)
    else:
        # 中度/深度都运行完整维护
        report = await service.run_maintenance(collection=collection, dry_run=dry_run, level=level)

    return report.to_dict()
