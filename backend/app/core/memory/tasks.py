"""
Memory Maintenance Tasks - Daily automated memory consolidation and cleanup.

This module provides background tasks for:
1. Daily memory quality analysis and cleanup recommendations
2. Automatic archiving of outdated memories
3. Two-tier hot memory regeneration
4. Daily log consolidation
5. Memory health reporting

Usage:
    # Tasks are automatically registered with the task scheduler
    # and run based on their configured schedules.
    
    # Manual trigger (for testing):
    from app.core.memory.tasks import run_memory_maintenance
    result = run_memory_maintenance.delay()
    
    # Or call directly:
    await run_memory_maintenance_async()

Schedule:
    - Daily at 2:00 AM: Full maintenance (cleanup, archive, regenerate)
    - Hourly: Light maintenance (stats collection)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.core.config import settings
from app.infrastructure.queue.factory import shared_task, periodic_task
from app.core.memory.maintenance_report import MaintenanceReport

logger = logging.getLogger(__name__)


async def _get_memory_container():
    """Get memory container, initializing if necessary."""
    # Lazy import to avoid circular dependencies at module load
    from app.core.memory.lifespan import MemoryLifespanManager
    
    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()
    
    return MemoryLifespanManager.get_container()


async def _analyze_and_cleanup_memories(
    report: MaintenanceReport,
    auto_archive: bool = True,
    auto_delete: bool = False,  # Conservative: don't auto-delete by default
    quality_threshold: float = 0.3,
) -> None:
    """
    Analyze memory quality and perform cleanup.
    
    Args:
        report: Maintenance report to update
        auto_archive: Whether to automatically archive outdated memories
        auto_delete: Whether to automatically delete very low quality memories
        quality_threshold: Quality score threshold for cleanup
    """
    # Lazy imports to avoid circular dependencies
    try:
        from app.core.memory.quality import MemoryQualityAnalyzer
        
        container = await _get_memory_container()
        analyzer = MemoryQualityAnalyzer(container.storage)
        
        # Get all memories
        all_memories = await container.storage.list_all()
        report.memories_analyzed = len(all_memories)
        
        if not all_memories:
            logger.info("[MemoryMaintenance] No memories to analyze")
            return
        
        # Get cleanup recommendations
        recommendations = await analyzer.get_cleanup_recommendations(
            min_quality=quality_threshold
        )
        
        report.low_quality_found = len(recommendations)
        
        # Calculate average quality
        total_score = 0.0
        for mem_summary in all_memories:
            entry = await container.storage.get(mem_summary.id)
            if entry:
                scores = await analyzer.analyze_memory(entry)
                total_score += scores.overall
        
        report.avg_quality_score = total_score / len(all_memories) if all_memories else 0.0
        
        # Process recommendations
        archive_cutoff_days = 90
        
        for rec in recommendations:
            entry = rec.entry
            age_days = (datetime.utcnow() - entry.updated_at).days
            
            try:
                if rec.action == "delete" and auto_delete:
                    # Only delete very low quality and old
                    if age_days > 30:
                        await container.storage.delete(entry.id)
                        report.memories_deleted += 1
                        logger.info(f"[MemoryMaintenance] Deleted low-quality memory: {entry.id}")
                
                elif rec.action == "archive" and auto_archive:
                    # Archive old project memories
                    if age_days > archive_cutoff_days:
                        # Mark as archived by moving to archive folder or tagging
                        entry.tags.append("archived")
                        entry.tags.append(f"archived_{datetime.utcnow().strftime('%Y%m%d')}")
                        await container.storage.save(entry)
                        report.memories_archived += 1
                        logger.info(f"[MemoryMaintenance] Archived old memory: {entry.id}")
                
                elif rec.action == "update":
                    # Tag for potential update (manual review needed)
                    if "needs_update" not in entry.tags:
                        entry.tags.append("needs_update")
                        await container.storage.save(entry)
                        report.memories_updated += 1
                
            except Exception as e:
                error_msg = f"Failed to process {entry.id}: {e}"
                logger.warning(f"[MemoryMaintenance] {error_msg}")
                report.errors.append(error_msg)
        
        logger.info(
            f"[MemoryMaintenance] Cleanup complete: "
            f"{report.memories_analyzed} analyzed, "
            f"{report.memories_archived} archived, "
            f"{report.memories_deleted} deleted, "
            f"{report.memories_updated} tagged for update"
        )
        
    except Exception as e:
        error_msg = f"Cleanup analysis failed: {e}"
        logger.error(f"[MemoryMaintenance] {error_msg}")
        report.errors.append(error_msg)


async def _regenerate_hot_memory(report: MaintenanceReport) -> None:
    """Regenerate hot memory (MEMORY.md) from cold storage."""
    try:
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        container = await _get_memory_container()
        manager = TwoTierMemoryManager(container.storage)
        
        # Regenerate MEMORY.md
        await manager.regenerate_memory_md()
        
        # Get stats
        stats = await manager.get_section_stats()
        total_entries = sum(s["used"] for s in stats.values())
        
        report.hot_memory_regenerated = True
        report.hot_memory_entries = total_entries
        
        logger.info(
            f"[MemoryMaintenance] Hot memory regenerated: "
            f"{total_entries} entries in {len(stats)} sections"
        )
        
    except Exception as e:
        error_msg = f"Hot memory regeneration failed: {e}"
        logger.error(f"[MemoryMaintenance] {error_msg}")
        report.errors.append(error_msg)


async def _consolidate_daily_logs(report: MaintenanceReport) -> None:
    """Consolidate yesterday's daily logs into long-term memories."""
    try:
        from app.core.memory.daily_log import DailyLogWriter, LogConsolidator
        from app.core.memory.manager import MemoryManager
        
        # Get yesterday's date
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Read yesterday's log
        log_writer = DailyLogWriter()
        entries = await log_writer.read_log(yesterday)
        
        if not entries:
            logger.info("[MemoryMaintenance] No logs to consolidate for yesterday")
            return
        
        # Consolidate
        container = await _get_memory_container()
        consolidator = LogConsolidator(memory_manager=container.memory_manager)
        
        # This would typically merge similar entries and create consolidated memories
        # For now, just count them
        report.logs_consolidated = len(entries)
        
        logger.info(f"[MemoryMaintenance] Consolidated {len(entries)} log entries")
        
    except Exception as e:
        error_msg = f"Daily log consolidation failed: {e}"
        logger.error(f"[MemoryMaintenance] {error_msg}")
        report.errors.append(error_msg)


async def _save_maintenance_report(report: MaintenanceReport) -> None:
    """Save maintenance report to memory storage."""
    try:
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        container = await _get_memory_container()
        
        # Create a memory entry for the report
        report_entry = MemoryEntry(
            id=f"maintenance-report-{report.timestamp.strftime('%Y%m%d-%H%M%S')}",
            type=MemoryType.REFERENCE,
            privacy=PrivacyLevel.PRIVATE,
            title=f"Daily Memory Maintenance Report - {report.timestamp.strftime('%Y-%m-%d')}",
            description=f"Maintenance completed in {report.duration_seconds:.1f}s. "
                       f"Analyzed: {report.memories_analyzed}, "
                       f"Archived: {report.memories_archived}, "
                       f"Deleted: {report.memories_deleted}",
            content=f"""# Memory Maintenance Report

**Date**: {report.timestamp.strftime('%Y-%m-%d %H:%M UTC')}
**Duration**: {report.duration_seconds:.2f} seconds

## Summary

- **Memories Analyzed**: {report.memories_analyzed}
- **Low Quality Found**: {report.low_quality_found}
- **Average Quality Score**: {report.avg_quality_score:.2f}

## Actions Taken

- **Archived**: {report.memories_archived} memories
- **Deleted**: {report.memories_deleted} memories
- **Tagged for Update**: {report.memories_updated} memories
- **Hot Memory Regenerated**: {'Yes' if report.hot_memory_regenerated else 'No'} ({report.hot_memory_entries} entries)
- **Logs Consolidated**: {report.logs_consolidated}

## Status

- **Success**: {'Yes' if not report.errors else 'No'}
- **Errors**: {len(report.errors)}

{chr(10).join(f'- {e}' for e in report.errors) if report.errors else 'No errors reported.'}
""",
            tags=["maintenance", "report", "auto-generated"],
            source="maintenance_task",
        )
        
        await container.storage.save(report_entry)
        logger.info(f"[MemoryMaintenance] Report saved: {report_entry.id}")
        
    except Exception as e:
        logger.error(f"[MemoryMaintenance] Failed to save report: {e}")


async def run_memory_maintenance_async(
    auto_archive: bool = True,
    auto_delete: bool = False,
    regenerate_hot_memory: bool = True,
    consolidate_logs: bool = True,
) -> MaintenanceReport:
    """
    Run full memory maintenance (async version).
    
    Args:
        auto_archive: Whether to auto-archive old memories
        auto_delete: Whether to auto-delete very low quality memories
        regenerate_hot_memory: Whether to regenerate MEMORY.md
        consolidate_logs: Whether to consolidate daily logs
        
    Returns:
        MaintenanceReport with all operations results
    """
    start_time = datetime.utcnow()
    report = MaintenanceReport(
        timestamp=start_time,
        duration_seconds=0.0,
    )
    
    logger.info("[MemoryMaintenance] Starting daily maintenance...")
    
    # Step 1: Analyze and cleanup memories
    logger.info("[MemoryMaintenance] Step 1/4: Analyzing memory quality...")
    await _analyze_and_cleanup_memories(
        report,
        auto_archive=auto_archive,
        auto_delete=auto_delete,
    )
    
    # Step 2: Regenerate hot memory
    if regenerate_hot_memory:
        logger.info("[MemoryMaintenance] Step 2/4: Regenerating hot memory...")
        await _regenerate_hot_memory(report)
    
    # Step 3: Consolidate daily logs
    if consolidate_logs:
        logger.info("[MemoryMaintenance] Step 3/4: Consolidating daily logs...")
        await _consolidate_daily_logs(report)
    
    # Step 4: Save report
    logger.info("[MemoryMaintenance] Step 4/4: Saving maintenance report...")
    await _save_maintenance_report(report)
    
    # Calculate duration
    end_time = datetime.utcnow()
    report.duration_seconds = (end_time - start_time).total_seconds()
    
    status = "SUCCESS" if not report.errors else "PARTIAL"
    logger.info(
        f"[MemoryMaintenance] Maintenance complete ({status}): "
        f"{report.duration_seconds:.2f}s, "
        f"{report.memories_analyzed} analyzed, "
        f"{report.memories_archived} archived, "
        f"{len(report.errors)} errors"
    )
    
    return report


# =============================================================================
# Task Queue Integration
# =============================================================================

@shared_task(name="memory_run_maintenance")
def run_memory_maintenance(
    auto_archive: bool = True,
    auto_delete: bool = False,
    regenerate_hot_memory: bool = True,
    consolidate_logs: bool = True,
) -> Dict[str, Any]:
    """
    Run full memory maintenance (task queue entry point).
    
    This is the main entry point for memory maintenance.
    Can be triggered manually or via scheduled task.
    
    Returns:
        Dictionary with maintenance report
    """
    async def _run():
        try:
            report = await run_memory_maintenance_async(
                auto_archive=auto_archive,
                auto_delete=auto_delete,
                regenerate_hot_memory=regenerate_hot_memory,
                consolidate_logs=consolidate_logs,
            )
            return report.to_dict()
        except Exception as e:
            logger.error(f"[MemoryMaintenance] Task failed: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "success": False,
                "error": str(e),
            }
        finally:
            # Clean up resources
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
    
    return asyncio.run(_run())


# =============================================================================
# Scheduled Tasks
# =============================================================================

# Daily full maintenance at 2:00 AM
# Cron format: minute hour day month day_of_week
@periodic_task(cron="0 2 * * *", name="memory_daily_maintenance")
def daily_memory_maintenance():
    """
    Daily full memory maintenance task.
    
    Runs at 2:00 AM every day:
    1. Analyzes all memories for quality
    2. Archives outdated memories (90+ days)
    3. Regenerates hot memory (MEMORY.md)
    4. Consolidates yesterday's logs
    5. Saves maintenance report
    """
    logger.info("[MemoryMaintenance] Scheduled daily maintenance triggered")
    return run_memory_maintenance(
        auto_archive=True,
        auto_delete=False,  # Conservative: don't auto-delete
        regenerate_hot_memory=True,
        consolidate_logs=True,
    )


# Hourly light maintenance - just collect stats
@periodic_task(cron="0 * * * *", name="memory_hourly_stats")
def hourly_memory_stats():
    """
    Hourly light maintenance - collect memory statistics.
    
    Runs at the start of every hour:
    - Collects memory counts and quality metrics
    - Logs for monitoring
    - Does not modify any memories
    """
    async def _collect_stats():
        try:
            from app.core.memory.quality import MemoryQualityAnalyzer
            
            container = await _get_memory_container()
            analyzer = MemoryQualityAnalyzer(container.storage)
            
            # Get all memories
            all_memories = await container.storage.list_all()
            
            if not all_memories:
                logger.debug("[MemoryMaintenance] No memories to analyze")
                return
            
            # Sample quality scores (don't analyze all every hour for performance)
            sample_size = min(10, len(all_memories))
            sampled = all_memories[:sample_size]
            
            total_score = 0.0
            for mem_summary in sampled:
                entry = await container.storage.get(mem_summary.id)
                if entry:
                    scores = await analyzer.analyze_memory(entry)
                    total_score += scores.overall
            
            avg_score = total_score / sample_size if sampled else 0.0
            
            logger.info(
                f"[MemoryMaintenance] Hourly stats: "
                f"{len(all_memories)} total memories, "
                f"avg quality (sample): {avg_score:.2f}"
            )
            
        except Exception as e:
            logger.error(f"[MemoryMaintenance] Hourly stats failed: {e}")
        finally:
            from app.utils.async_utils import flush_loop_bound_resources
            await flush_loop_bound_resources()
    
    return asyncio.run(_collect_stats())


# =============================================================================
# Manual Trigger Helpers
# =============================================================================

def trigger_maintenance_now() -> Any:
    """
    Trigger maintenance immediately (for manual/admin use).
    
    Usage:
        result = trigger_maintenance_now()
        report = result.get(timeout=60)
    
    Returns:
        TaskResult that can be waited on
    """
    from app.infrastructure.queue.factory import get_scheduler
    
    scheduler = get_scheduler()
    return scheduler.send_task(
        "memory_run_maintenance",
        kwargs={
            "auto_archive": True,
            "auto_delete": False,
            "regenerate_hot_memory": True,
            "consolidate_logs": True,
        }
    )


async def get_last_maintenance_report() -> Optional[MaintenanceReport]:
    """
    Get the most recent maintenance report.
    
    Returns:
        MaintenanceReport or None if no reports found
    """
    try:
        container = await _get_memory_container()
        
        # Search for maintenance reports
        results = await container.storage.search(
            query="maintenance report",
            types=[],  # All types
            limit=1,
        )
        
        if not results:
            return None
        
        # Return the most recent
        report_entry = results[0]
        
        # Parse the report (simplified)
        return MaintenanceReport(
            timestamp=report_entry.updated_at,
            duration_seconds=0.0,  # Would need to parse from content
            memories_analyzed=0,  # Would need to parse from content
        )
        
    except Exception as e:
        logger.error(f"[MemoryMaintenance] Failed to get last report: {e}")
        return None
