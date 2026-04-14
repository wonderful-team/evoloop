"""
Celery tasks for memory system maintenance.

Includes:
- Nightly consolidation of daily logs
- Memory quality analysis
- Cleanup of stale memories
"""

import logging
from datetime import datetime, timedelta

# Unified task queue (Huey in embedded mode, Celery in full mode)
from app.infrastructure.queue.factory import get_scheduler

logger = logging.getLogger(__name__)

# Get scheduler instance
_task_scheduler = get_scheduler()


# Create task decorator
def _task(name, **kwargs):
    def decorator(f):
        return _task_scheduler.task(f, name=name, **kwargs)
    return decorator


@_task(name="memory.nightly_consolidation")
def nightly_consolidation(days: int = 1):
    """
    Run nightly consolidation of daily memory logs.
    
    This task:
    1. Reads yesterday's (or specified days') daily logs
    2. Clusters similar memories
    3. Creates consolidated topic memories
    4. Regenerates MEMORY.md (Two-Tier Architecture)
    
    Args:
        days: Number of recent days to consolidate (default: 1)
    
    Schedule:
        Run at 3:00 AM daily
    
    Example:
        # Run manually
        nightly_consolidation.delay()
        
        # Run for last 3 days
        nightly_consolidation.delay(days=3)
    """
    import asyncio
    
    async def run():
        from app.core.memory.daily_log import log_consolidator
        from app.core.memory import MemoryContainer, MemoryConfig
        
        logger.info(f"[NightlyConsolidation] Starting consolidation for last {days} days")
        
        results = {
            "status": "success",
            "consolidated_count": 0,
            "memory_md_updated": False,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Use global singleton via MemoryLifespanManager
        from app.core.memory.lifespan import MemoryLifespanManager
        
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        manager = MemoryLifespanManager.get_manager()
        
        try:
            # Step 1: Consolidate daily logs
            consolidated = await log_consolidator.consolidate_recent(days=days)
            results["consolidated_count"] = len(consolidated)
            logger.info(f"[NightlyConsolidation] Created {len(consolidated)} consolidated memories")
            
            # Step 2: Regenerate MEMORY.md (Two-Tier Architecture)
            logger.info("[NightlyConsolidation] Regenerating MEMORY.md")
            await manager.regenerate_memory_md()
            results["memory_md_updated"] = True
            logger.info("[NightlyConsolidation] MEMORY.md updated successfully")
            
        except Exception as e:
            logger.error(f"[NightlyConsolidation] Failed: {e}")
            results["status"] = "error"
            results["error"] = str(e)
        
        return results
    
    # Run async code in sync task
    return asyncio.run(run())


@_task(name="memory.quality_analysis")
def analyze_memory_quality(project_id: int = None):
    """
    Analyze memory quality and generate cleanup recommendations.
    
    Args:
        project_id: Optional project ID to scope analysis
    
    Returns:
        Quality report with recommendations
    """
    import asyncio
    
    async def run():
        from app.core.memory.quality import quality_analyzer
        
        logger.info(f"[QualityAnalysis] Analyzing memory quality")
        
        try:
            report = await quality_analyzer.generate_quality_report(project_id)
            
            recommendations = report.get("recommendations", [])
            
            logger.info(
                f"[QualityAnalysis] Analyzed {report['total']} memories, "
                f"found {report['low_quality_count']} low quality, "
                f"{len(recommendations)} cleanup recommendations"
            )
            
            return {
                "status": "success",
                "report": report,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"[QualityAnalysis] Failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    return asyncio.run(run())


@_task(name="memory.cleanup_stale")
def cleanup_stale_memories(dry_run: bool = True, min_quality: float = 0.2):
    """
    Clean up stale memories based on quality recommendations.
    
    Args:
        dry_run: If True, only report what would be done
        min_quality: Minimum quality threshold for keeping memories
    
    Returns:
        Cleanup report
    """
    import asyncio
    
    async def run():
        from app.core.memory.quality import quality_analyzer
        
        logger.info(f"[Cleanup] Starting stale memory cleanup (dry_run={dry_run})")
        
        try:
            recommendations = await quality_analyzer.get_cleanup_recommendations(
                min_quality=min_quality
            )
            
            to_archive = [r for r in recommendations if r.action == "archive"]
            to_delete = [r for r in recommendations if r.action == "delete"]
            
            if dry_run:
                logger.info(
                    f"[Cleanup] DRY RUN: Would archive {len(to_archive)}, "
                    f"delete {len(to_delete)}"
                )
            else:
                # Actually perform cleanup
                deleted_count = 0
                archived_count = 0
                
                # TODO: Implement actual deletion/archival
                # This would move files to an archive directory
                
                logger.info(
                    f"[Cleanup] Archived {archived_count}, deleted {deleted_count}"
                )
            
            return {
                "status": "success",
                "dry_run": dry_run,
                "to_archive": len(to_archive),
                "to_delete": len(to_delete),
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"[Cleanup] Failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    return asyncio.run(run())


@_task(name="memory.daily_report")
def generate_daily_memory_report():
    """
    Generate a daily report of memory activity.
    
    Returns:
        Daily activity report
    """
    import asyncio
    
    async def run():
        from app.core.memory.daily_log import daily_log_writer
        
        logger.info("[DailyReport] Generating daily memory report")
        
        try:
            stats = await daily_log_writer.get_stats()
            
            # Get yesterday's stats
            yesterday = datetime.utcnow() - timedelta(days=1)
            yesterday_stats = await daily_log_writer.get_stats(yesterday)
            
            report = {
                "today": stats,
                "yesterday": yesterday_stats,
                "available_dates": len(await daily_log_writer.list_available_dates()),
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            logger.info(f"[DailyReport] Generated report: {stats}")
            
            return {
                "status": "success",
                "report": report,
            }
            
        except Exception as e:
            logger.error(f"[DailyReport] Failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    return asyncio.run(run())


@_task(name="memory.regenerate_hot_memory")
def regenerate_hot_memory():
    """
    Regenerate MEMORY.md from cold memory.
    
    This updates the hot memory (Tier 1) based on the current
    state of cold memory (Tier 2), applying budgets and rankings.
    
    Schedule:
        Run every 4 hours to keep hot memory fresh
    """
    import asyncio
    
    async def run():
        from app.core.memory.lifespan import MemoryLifespanManager
        
        logger.info("[RegenerateHotMemory] Regenerating MEMORY.md")
        
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        manager = MemoryLifespanManager.get_manager()
        
        try:
            await manager.regenerate_memory_md()
            
            return {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"[RegenerateHotMemory] Failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    return asyncio.run(run())


# Celery Beat Schedule Configuration
# Add to celery_app.conf.beat_schedule in your Celery config:
MEMORY_BEAT_SCHEDULE = {
    "nightly-consolidation": {
        "task": "memory.nightly_consolidation",
        "schedule": "crontab(hour=3, minute=0)",  # 3:00 AM daily
        "args": (1,),  # Consolidate yesterday
    },
    "regenerate-hot-memory": {
        "task": "memory.regenerate_hot_memory",
        "schedule": "crontab(hour=*/4, minute=0)",  # Every 4 hours
    },
    "weekly-quality-analysis": {
        "task": "memory.quality_analysis",
        "schedule": "crontab(day_of_week=0, hour=2, minute=0)",  # Sunday 2:00 AM
    },
    "daily-memory-report": {
        "task": "memory.daily_report",
        "schedule": "crontab(hour=8, minute=0)",  # 8:00 AM daily
    },
}
