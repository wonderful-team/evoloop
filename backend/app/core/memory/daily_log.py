"""
KAIROS Daily Log Mode - Append-only daily logging with nightly consolidation.

This module implements:
1. Daily append-only logs for all memory writes
2. Automatic nightly consolidation into topic memories
3. Log rotation and cleanup

Architecture:
    ~/.evoloop/memory/
    ├── logs/
    │   └── 2026/
    │       └── 04/
    │           ├── 2026-04-01.md     # Daily log
    │           ├── 2026-04-02.md
    │           └── ...
    ├── private/                      # Consolidated private memories
    └── team/                         # Consolidated team memories

Usage:
    # Automatic logging (happens on every memory write)
    await memory_manager.save_memory(entry)  # Also appends to daily log
    
    # Manual consolidation (usually run by nightly task)
    from app.core.memory.manager import MemoryManager
    
    memory_manager = MemoryManager()  # or use factory
    consolidator = LogConsolidator(memory_manager=memory_manager)
    await consolidator.consolidate_date(datetime.utcnow() - timedelta(days=1))
"""
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.core.config import settings
from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


class LogEntry(BaseModel, LegacyDictMixin):
    """An entry in the daily log."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    memory_id: str
    memory_type: str
    title: str
    description: str
    user_id: Optional[str] = None
    project_id: Optional[int] = None
    
    def to_markdown(self) -> str:
        """Convert to markdown format for daily log."""
        ts = self.timestamp.strftime("%H:%M:%S")
        user_info = f" | user:{self.user_id}" if self.user_id else ""
        project_info = f" | project:{self.project_id}" if self.project_id else ""
        
        return (
            f"- [{ts}] **{self.memory_type.upper()}**: {self.title}\n"
            f"  - ID: `{self.memory_id}`{user_info}{project_info}\n"
            f"  - {self.description[:100]}{'...' if len(self.description) > 100 else ''}\n"
        )
    
    @classmethod
    def from_memory_entry(cls, entry: MemoryEntry) -> "LogEntry":
        """Create LogEntry from MemoryEntry."""
        return cls(
            timestamp=datetime.utcnow(),
            memory_id=entry.id,
            memory_type=entry.type.value,
            title=entry.title,
            description=entry.description,
            user_id=entry.user_id,
            project_id=entry.project_id,
        )


class DailyLogWriter:
    """
    Append-only daily log writer for KAIROS mode.
    
    Writes all memory operations to daily logs for later consolidation.
    """
    
    def __init__(self, root_path: Optional[Path] = None):
        self.root = Path(root_path) if root_path else Path(settings.BRAIN_MEMORY_ROOT)
        self.logs_dir = self.root / "logs"
    
    def _get_log_path(self, date: Optional[datetime] = None) -> Path:
        """Get the log file path for a given date."""
        date = date or datetime.utcnow()
        return (
            self.logs_dir /
            str(date.year) /
            f"{date.month:02d}" /
            f"{date.year}-{date.month:02d}-{date.day:02d}.md"
        )
    
    async def append(self, entry: MemoryEntry) -> None:
        """
        Append a memory entry to today's log.
        
        This is called automatically whenever a memory is saved.
        """
        log_path = self._get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        log_entry = LogEntry.from_memory_entry(entry)
        
        # Write to log file (append mode)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._write_to_log,
            log_path,
            log_entry,
        )
        
        logger.debug(f"[DailyLog] Appended {entry.id} to {log_path.name}")
    
    def _write_to_log(self, log_path: Path, log_entry: LogEntry) -> None:
        """Synchronous write to log file."""
        # Check if file exists and needs header
        needs_header = not log_path.exists()
        
        with open(log_path, "a", encoding="utf-8") as f:
            if needs_header:
                date_str = log_entry.timestamp.strftime("%Y-%m-%d")
                f.write(f"# Memory Log: {date_str}\n\n")
                f.write("Auto-generated log of memory operations.\n\n")
            
            f.write(log_entry.to_markdown())
            f.write("\n")
    
    async def read_log(self, date: Optional[datetime] = None) -> List[LogEntry]:
        """Read and parse a daily log file."""
        log_path = self._get_log_path(date)
        
        if not log_path.exists():
            return []
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._parse_log_file,
            log_path,
        )
    
    def _parse_log_file(self, log_path: Path) -> List[LogEntry]:
        """Parse a log file into LogEntry objects."""
        entries = []
        
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse log entries
        # Format: - [HH:MM:SS] **TYPE**: Title
        pattern = r'- \[(\d{2}:\d{2}:\d{2})\] \*\*(\w+)\*\*: (.+)\n  - ID: `([^`]+)`(?: \| user:(\w+))?(?: \| project:(\d+))?\n  - (.+)'
        
        date_str = log_path.stem  # YYYY-MM-DD
        
        for match in re.finditer(pattern, content):
            time_str, mem_type, title, mem_id, user_id, project_id, desc = match.groups()
            
            timestamp = datetime.strptime(
                f"{date_str} {time_str}",
                "%Y-%m-%d %H:%M:%S"
            )
            
            entries.append(LogEntry(
                timestamp=timestamp,
                memory_id=mem_id,
                memory_type=mem_type.lower(),
                title=title,
                description=desc,
                user_id=user_id,
                project_id=int(project_id) if project_id else None,
            ))
        
        return entries
    
    async def list_available_dates(self) -> List[datetime]:
        """List all dates that have log files."""
        dates = []
        
        if not self.logs_dir.exists():
            return dates
        
        for year_dir in self.logs_dir.iterdir():
            if not year_dir.is_dir():
                continue
            
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                
                for log_file in month_dir.glob("*.md"):
                    # Parse filename YYYY-MM-DD.md
                    try:
                        date = datetime.strptime(log_file.stem, "%Y-%m-%d")
                        dates.append(date)
                    except ValueError:
                        continue
        
        return sorted(dates)
    
    async def get_stats(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """Get statistics for a daily log."""
        entries = await self.read_log(date)
        
        if not entries:
            return {"count": 0}
        
        type_counts = {}
        user_counts = {}
        project_counts = {}
        
        for entry in entries:
            type_counts[entry.memory_type] = type_counts.get(entry.memory_type, 0) + 1
            
            if entry.user_id:
                user_counts[entry.user_id] = user_counts.get(entry.user_id, 0) + 1
            
            if entry.project_id:
                project_counts[entry.project_id] = project_counts.get(entry.project_id, 0) + 1
        
        return {
            "count": len(entries),
            "by_type": type_counts,
            "by_user": user_counts,
            "by_project": project_counts,
            "first_entry": entries[0].timestamp.isoformat(),
            "last_entry": entries[-1].timestamp.isoformat(),
        }


class LogConsolidator:
    """
    Consolidate daily logs into topic memories.
    
    This runs nightly to:
    1. Read yesterday's log
    2. Cluster similar entries by topic
    3. Create or update consolidated memories
    """
    
    # Minimum entries to create a consolidated memory
    MIN_CLUSTER_SIZE = 2
    
    # Maximum age of log to consolidate (days)
    MAX_CONSOLIDATION_AGE = 7
    
    def __init__(
        self,
        memory_manager,
        root_path: Optional[Path] = None,
    ):
        """
        Initialize log consolidator.
        
        Args:
            memory_manager: Memory manager instance (required)
            root_path: Root path for memory files (legacy, prefer config).
        """
        self._memory_manager = memory_manager
        self.root = Path(root_path) if root_path else Path(settings.BRAIN_MEMORY_ROOT)
        self.log_writer = DailyLogWriter(root_path)
    
    async def consolidate_date(self, date: datetime) -> List[MemoryEntry]:
        """
        Consolidate a specific date's log.
        
        Args:
            date: The date to consolidate
            
        Returns:
            List of consolidated memory entries created
        """
        entries = await self.log_writer.read_log(date)
        
        if len(entries) < self.MIN_CLUSTER_SIZE:
            logger.info(f"[Consolidation] Not enough entries for {date.date()}: {len(entries)}")
            return []
        
        # Cluster entries by type and topic similarity
        clusters = self._cluster_entries(entries)
        
        # Create consolidated memories
        consolidated = []
        for cluster in clusters:
            if len(cluster) >= self.MIN_CLUSTER_SIZE:
                memory = await self._create_consolidated_memory(cluster, date)
                if memory:
                    consolidated.append(memory)
        
        logger.info(f"[Consolidation] Created {len(consolidated)} memories from {date.date()}")
        return consolidated
    
    def _cluster_entries(self, entries: List[LogEntry]) -> List[List[LogEntry]]:
        """
        Cluster log entries by type and topic similarity.
        
        Simple implementation: group by type first, then by keyword overlap.
        """
        # Group by type
        by_type: Dict[str, List[LogEntry]] = {}
        for entry in entries:
            by_type.setdefault(entry.memory_type, []).append(entry)
        
        clusters = []
        
        for mem_type, type_entries in by_type.items():
            # Simple clustering by title similarity
            type_clusters = self._cluster_by_similarity(type_entries)
            clusters.extend(type_clusters)
        
        return clusters
    
    def _cluster_by_similarity(self, entries: List[LogEntry]) -> List[List[LogEntry]]:
        """Cluster entries by title/description similarity."""
        if not entries:
            return []
        
        clusters: List[List[LogEntry]] = []
        
        for entry in entries:
            # Find best matching cluster
            best_cluster = None
            best_score = 0.0
            
            entry_words = set(entry.title.lower().split())
            
            for cluster in clusters:
                # Calculate similarity with cluster
                cluster_words = set()
                for e in cluster:
                    cluster_words.update(e.title.lower().split())
                
                if not cluster_words:
                    continue
                
                # Jaccard similarity
                intersection = len(entry_words & cluster_words)
                union = len(entry_words | cluster_words)
                score = intersection / union if union > 0 else 0
                
                if score > 0.3 and score > best_score:  # 30% similarity threshold
                    best_score = score
                    best_cluster = cluster
            
            if best_cluster is not None:
                best_cluster.append(entry)
            else:
                clusters.append([entry])
        
        return clusters
    
    async def _create_consolidated_memory(
        self,
        cluster: List[LogEntry],
        date: datetime,
    ) -> Optional[MemoryEntry]:
        """Create a consolidated memory from a cluster of log entries."""
        if not cluster:
            return None
        
        # Determine type (all in cluster should be same type)
        mem_type = MemoryType(cluster[0].memory_type)
        
        # Create consolidated title
        topics = set()
        for entry in cluster:
            # Extract key terms from title
            words = entry.title.lower().split()
            topics.update(w for w in words if len(w) > 3)
        
        title = f"Daily Summary: {cluster[0].memory_type.title()} ({date.strftime('%Y-%m-%d')})"
        
        # Create consolidated content
        content_lines = [
            f"## Consolidated from {len(cluster)} memories on {date.strftime('%Y-%m-%d')}",
            "",
            "### Topics Covered",
        ]
        
        for entry in cluster:
            content_lines.append(f"- {entry.title}")
        
        content_lines.extend([
            "",
            "### Details",
            "",
        ])
        
        for entry in cluster:
            content_lines.append(f"**{entry.title}** (at {entry.timestamp.strftime('%H:%M')})")
            content_lines.append(f"- {entry.description}")
            content_lines.append("")
        
        content = "\n".join(content_lines)
        
        # Create memory entry
        memory = MemoryEntry(
            id=f"consolidated_{date.strftime('%Y%m%d')}_{cluster[0].memory_type}",
            type=mem_type,
            privacy=PrivacyLevel.TEAM if mem_type in (MemoryType.PROJECT, MemoryType.REFERENCE) else PrivacyLevel.PRIVATE,
            title=title,
            description=f"Consolidated {len(cluster)} {cluster[0].memory_type} memories from {date.strftime('%Y-%m-%d')}",
            content=content,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            tags=["consolidated", "daily-summary"],
            source="nightly_consolidation",
        )
        
        # Save to storage
        await self._memory_manager.save_memory(memory)
        
        return memory
    
    async def consolidate_recent(self, days: int = 1) -> List[MemoryEntry]:
        """
        Consolidate recent days' logs.
        
        Args:
            days: Number of recent days to consolidate
            
        Returns:
            List of all consolidated memories created
        """
        all_consolidated = []
        
        for i in range(1, days + 1):
            date = datetime.utcnow() - timedelta(days=i)
            consolidated = await self.consolidate_date(date)
            all_consolidated.extend(consolidated)
        
        return all_consolidated
    
    async def get_consolidation_report(self, days: int = 7) -> Dict[str, Any]:
        """Get a report of consolidation status."""
        dates = await self.log_writer.list_available_dates()
        
        # Filter to recent dates
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent_dates = [d for d in dates if d >= cutoff]
        
        report = {
            "period_days": days,
            "dates_with_logs": len(recent_dates),
            "daily_stats": {},
            "total_entries": 0,
        }
        
        for date in recent_dates:
            stats = await self.log_writer.get_stats(date)
            report["daily_stats"][date.strftime("%Y-%m-%d")] = stats
            report["total_entries"] += stats["count"]
        
        return report


# Global instances
daily_log_writer = DailyLogWriter()


# Convenience functions
async def append_to_daily_log(entry: MemoryEntry) -> None:
    """Append a memory entry to the daily log."""
    await daily_log_writer.append(entry)


async def get_daily_log_stats(date: Optional[datetime] = None) -> Dict[str, Any]:
    """Get statistics for a daily log."""
    return await daily_log_writer.get_stats(date)
