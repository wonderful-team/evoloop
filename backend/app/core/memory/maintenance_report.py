"""
Memory Maintenance Report - Standalone module to avoid import cycles.

This module contains only the data classes for maintenance reports,
allowing them to be imported without triggering the full memory system imports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any


@dataclass
class MaintenanceReport:
    """Report of memory maintenance operations."""
    timestamp: datetime
    duration_seconds: float
    
    # Cleanup stats
    memories_analyzed: int = 0
    memories_archived: int = 0
    memories_deleted: int = 0
    memories_updated: int = 0
    
    # Quality stats
    low_quality_found: int = 0
    avg_quality_score: float = 0.0
    
    # Two-tier stats
    hot_memory_regenerated: bool = False
    hot_memory_entries: int = 0
    
    # Log consolidation
    logs_consolidated: int = 0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": round(self.duration_seconds, 2),
            "cleanup": {
                "analyzed": self.memories_analyzed,
                "archived": self.memories_archived,
                "deleted": self.memories_deleted,
                "updated": self.memories_updated,
            },
            "quality": {
                "low_quality_found": self.low_quality_found,
                "avg_score": round(self.avg_quality_score, 2),
            },
            "two_tier": {
                "regenerated": self.hot_memory_regenerated,
                "entries": self.hot_memory_entries,
            },
            "logs": {
                "consolidated": self.logs_consolidated,
            },
            "errors": self.errors,
            "success": len(self.errors) == 0,
        }
