"""
Usage Ranking - OS-native application activity analysis.

Provides UsageRanker which queries platform-specific APIs
to determine which applications are most actively used,
enabling prioritization of exploration.
"""

from app.core.environment.usage.ranker import AppUsageRecord, UsageRanker

__all__ = ["AppUsageRecord", "UsageRanker"]
