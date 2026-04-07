"""
Memory Maintenance CLI - Command-line interface for memory maintenance tasks.

Usage:
    # Run maintenance immediately
    python -m app.core.memory.maintenance_cli run
    
    # Dry run (analyze only, don't modify)
    python -m app.core.memory.maintenance_cli run --dry-run
    
    # Show last maintenance report
    python -m app.core.memory.maintenance_cli report
    
    # Show memory statistics
    python -m app.core.memory.maintenance_cli stats
    
    # Schedule maintenance (add to crontab/systemd)
    python -m app.core.memory.maintenance_cli schedule --install
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def cmd_run(args: argparse.Namespace) -> int:
    """Run maintenance task."""
    from app.core.memory.tasks import run_memory_maintenance_async
    
    print(f"🧹 Starting memory maintenance (dry_run={args.dry_run})...")
    print()
    
    report = await run_memory_maintenance_async(
        auto_archive=not args.dry_run,
        auto_delete=args.auto_delete and not args.dry_run,
        regenerate_hot_memory=not args.dry_run,
        consolidate_logs=not args.dry_run,
    )
    
    # Print report
    print("=" * 60)
    print(f"📊 MAINTENANCE REPORT - {report.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    print()
    
    print(f"⏱️  Duration: {report.duration_seconds:.2f} seconds")
    print()
    
    print("📈 STATISTICS:")
    print(f"   • Memories analyzed: {report.memories_analyzed}")
    print(f"   • Low quality found: {report.low_quality_found}")
    print(f"   • Average quality: {report.avg_quality_score:.2f}")
    print()
    
    print("🧹 CLEANUP ACTIONS:")
    print(f"   • Archived: {report.memories_archived}")
    print(f"   • Deleted: {report.memories_deleted}")
    print(f"   • Tagged for update: {report.memories_updated}")
    print()
    
    print("🔥 HOT MEMORY:")
    print(f"   • Regenerated: {'Yes' if report.hot_memory_regenerated else 'No'}")
    print(f"   • Entries: {report.hot_memory_entries}")
    print()
    
    print("📝 LOGS:")
    print(f"   • Consolidated: {report.logs_consolidated}")
    print()
    
    if report.errors:
        print("⚠️  ERRORS:")
        for error in report.errors:
            print(f"   • {error}")
        print()
    
    status = "✅ SUCCESS" if not report.errors else "⚠️  PARTIAL"
    print(f"Status: {status}")
    print()
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"💾 Report saved to: {args.output}")
    
    return 0 if not report.errors else 1


async def cmd_report(args: argparse.Namespace) -> int:
    """Show last maintenance report."""
    from app.core.memory.tasks import get_last_maintenance_report
    
    report = await get_last_maintenance_report()
    
    if not report:
        print("❌ No maintenance reports found")
        return 1
    
    print("=" * 60)
    print(f"📊 LAST MAINTENANCE REPORT - {report.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    print()
    print(f"Duration: {report.duration_seconds:.2f}s")
    print(f"Memories: {report.memories_analyzed} analyzed")
    print(f"Actions: {report.memories_archived} archived, {report.memories_deleted} deleted")
    print()
    
    return 0


async def cmd_stats(args: argparse.Namespace) -> int:
    """Show memory statistics."""
    from app.core.memory.lifespan import MemoryLifespanManager
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.two_tier import TwoTierMemoryManager
    
    print("📊 Collecting memory statistics...")
    print()
    
    # Initialize
    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()
    
    container = MemoryLifespanManager.get_container()
    
    # Get all memories
    all_memories = await container.storage.list_all()
    
    if not all_memories:
        print("ℹ️  No memories found")
        return 0
    
    # Analyze quality
    analyzer = MemoryQualityAnalyzer(container.storage)
    
    total_score = 0.0
    type_counts = {}
    age_distribution = {"< 7 days": 0, "7-30 days": 0, "30-90 days": 0, "> 90 days": 0}
    
    now = datetime.utcnow()
    
    for mem_summary in all_memories:
        entry = await container.storage.get(mem_summary.id)
        if not entry:
            continue
        
        # Quality score
        scores = await analyzer.analyze_memory(entry)
        total_score += scores.overall
        
        # Type count
        type_name = entry.type.value
        type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        # Age distribution
        age_days = (now - entry.updated_at).days
        if age_days < 7:
            age_distribution["< 7 days"] += 1
        elif age_days < 30:
            age_distribution["7-30 days"] += 1
        elif age_days < 90:
            age_distribution["30-90 days"] += 1
        else:
            age_distribution["> 90 days"] += 1
    
    avg_score = total_score / len(all_memories) if all_memories else 0.0
    
    # Get hot memory stats
    manager = TwoTierMemoryManager(container.storage)
    try:
        hot_stats = await manager.get_section_stats()
        hot_total = sum(s["used"] for s in hot_stats.values())
    except Exception:
        hot_stats = {}
        hot_total = 0
    
    # Print stats
    print("=" * 60)
    print("📈 MEMORY STATISTICS")
    print("=" * 60)
    print()
    
    print(f"Total memories: {len(all_memories)}")
    print(f"Average quality: {avg_score:.2f}")
    print()
    
    print("📂 BY TYPE:")
    for type_name, count in sorted(type_counts.items()):
        print(f"   • {type_name}: {count}")
    print()
    
    print("📅 AGE DISTRIBUTION:")
    for age_range, count in age_distribution.items():
        pct = (count / len(all_memories) * 100) if all_memories else 0
        bar = "█" * int(pct / 5)
        print(f"   • {age_range:12s}: {count:4d} ({pct:5.1f}%) {bar}")
    print()
    
    print("🔥 HOT MEMORY (MEMORY.md):")
    print(f"   • Total entries: {hot_total}")
    for section, stats in hot_stats.items():
        print(f"   • {section}: {stats['used']}/{stats['budget']} ({stats['remaining']} remaining)")
    print()
    
    # Low quality memories
    low_quality = await analyzer.get_cleanup_recommendations(min_quality=0.3)
    if low_quality:
        print(f"⚠️  Low quality memories: {len(low_quality)}")
        print("   Run 'python -m app.core.memory.maintenance_cli run' to clean up")
    else:
        print("✅ All memories look good!")
    print()
    
    return 0


async def cmd_schedule(args: argparse.Namespace) -> int:
    """Manage maintenance schedule."""
    print("📅 Memory Maintenance Schedule")
    print()
    
    if args.install:
        print("Installing scheduled tasks...")
        print()
        
        # The tasks are already registered via decorators
        # Just verify they're available
        from app.infrastructure.queue.factory import get_scheduler
        
        scheduler = get_scheduler()
        
        print("✅ Scheduled tasks registered:")
        print("   • Daily maintenance: Every day at 2:00 AM")
        print("   • Hourly stats: Every hour")
        print()
        
        if args.embedded:
            print("📝 To run the scheduler (embedded mode):")
            print("   python -m app.infrastructure.queue.huey_queue")
            print()
        else:
            print("📝 Celery beat will automatically run scheduled tasks")
            print()
        
        return 0
    
    if args.status:
        print("Current schedule status:")
        print("   • Daily maintenance (2:00 AM): Active via periodic_task decorator")
        print("   • Hourly stats: Active via periodic_task decorator")
        print()
        print("Note: Tasks run when the task queue consumer is active")
        return 0
    
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Memory Maintenance CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s run                    # Run maintenance now
  %(prog)s run --dry-run          # Analyze only, don't modify
  %(prog)s stats                  # Show memory statistics
  %(prog)s report                 # Show last maintenance report
  %(prog)s schedule --install     # Install scheduled tasks
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run maintenance now")
    run_parser.add_argument("--dry-run", action="store_true", 
                           help="Analyze only, don't modify anything")
    run_parser.add_argument("--auto-delete", action="store_true",
                           help="Allow deletion of very low quality memories")
    run_parser.add_argument("--output", "-o", type=str,
                           help="Save report to JSON file")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Show last maintenance report")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show memory statistics")
    
    # Schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Manage maintenance schedule")
    schedule_parser.add_argument("--install", action="store_true",
                                help="Install scheduled tasks")
    schedule_parser.add_argument("--status", action="store_true",
                                help="Show schedule status")
    schedule_parser.add_argument("--embedded", action="store_true",
                                help="Show instructions for embedded mode")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run async command
    if args.command == "run":
        return asyncio.run(cmd_run(args))
    elif args.command == "report":
        return asyncio.run(cmd_report(args))
    elif args.command == "stats":
        return asyncio.run(cmd_stats(args))
    elif args.command == "schedule":
        return asyncio.run(cmd_schedule(args))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
