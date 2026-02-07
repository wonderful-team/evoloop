"""
Adaptive Capability Boundary Manager

Dynamically learns and manages capability boundaries based on runtime failures.
Boundaries are injected into prompts to prevent repeated failures.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BoundaryCategory(str, Enum):
    """Categories of capability boundaries"""
    NETWORK = "network"
    PERMISSION = "permission"
    DEVICE = "device"
    TOOL = "tool"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


@dataclass
class DynamicBoundary:
    """A learned capability boundary with TTL"""
    description: str
    category: BoundaryCategory
    source_tool: str
    source_error: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    occurrence_count: int = 1
    
    @property
    def is_expired(self) -> bool:
        """Check if boundary has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def extend_ttl(self, hours: int = 1) -> None:
        """Extend the boundary TTL on repeated failures."""
        self.expires_at = datetime.now() + timedelta(hours=hours)
        self.occurrence_count += 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "description": self.description,
            "category": self.category.value,
            "source_tool": self.source_tool,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "occurrence_count": self.occurrence_count
        }


class AdaptiveBoundaryManager:
    """
    Manages dynamic capability boundaries learned from tool failures.
    
    Features:
    - Automatic failure attribution (network, permission, device, etc.)
    - TTL-based boundary expiration (default 1 hour, extended on repeat)
    - Occurrence counting for persistent issues
    - Integration with AwakenedState.capability_boundaries
    
    Usage:
        # On tool failure
        await boundary_manager.on_tool_failure("adb_tap", timeout_error)
        
        # Get all boundaries for prompt injection
        boundaries = boundary_manager.get_all_boundaries()
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._boundaries: Dict[str, DynamicBoundary] = {}
            cls._instance._static_boundaries: List[str] = []
        return cls._instance
    
    def set_static_boundaries(self, boundaries: List[str]) -> None:
        """Set the base static boundaries from environment probe."""
        self._static_boundaries = list(boundaries)
    
    async def on_tool_failure(
        self, 
        tool_name: str, 
        error: Exception, 
        context: Optional[Dict] = None
    ) -> Optional[DynamicBoundary]:
        """
        Process a tool failure and potentially create a new boundary.
        
        Args:
            tool_name: Name of the failed tool
            error: The exception that was raised
            context: Additional context (device_id, network status, etc.)
            
        Returns:
            The created or updated DynamicBoundary, if applicable
        """
        error_str = str(error).lower()
        
        # 1. Attribute the failure to a category
        category, mitigation = self._attribute_failure(error_str, tool_name)
        
        if category == BoundaryCategory.UNKNOWN:
            logger.debug(f"Unknown failure type for {tool_name}: {error}")
            return None
        
        # 2. Create boundary key
        boundary_key = f"{tool_name}:{category.value}"
        
        # 3. Check if boundary already exists
        if boundary_key in self._boundaries:
            existing = self._boundaries[boundary_key]
            if not existing.is_expired:
                existing.extend_ttl(hours=2)  # Extend on repeated failure
                logger.info(f"🔄 Extended boundary TTL: {boundary_key} (count: {existing.occurrence_count})")
                return existing
        
        # 4. Create new boundary
        boundary = DynamicBoundary(
            description=mitigation,
            category=category,
            source_tool=tool_name,
            source_error=error_str[:200],
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        self._boundaries[boundary_key] = boundary
        logger.warning(f"⚠️ New dynamic boundary: {mitigation}")
        
        # 5. Publish event
        from app.domain.environment.events import event_bus, BoundaryLearnedEvent
        await event_bus.publish(BoundaryLearnedEvent(
            tool_name=tool_name,
            category=category.value,
            description=mitigation
        ))
        
        return boundary
    
    def _attribute_failure(self, error_str: str, tool_name: str) -> tuple[BoundaryCategory, str]:
        """
        Analyze error message to determine failure category and mitigation.
        
        Returns:
            Tuple of (category, mitigation_description)
        """
        # Network issues
        if any(kw in error_str for kw in ["timeout", "connection refused", "network", "unreachable", "timed out"]):
            return (
                BoundaryCategory.NETWORK,
                f"Tool '{tool_name}' may timeout under poor network conditions. Check connectivity first."
            )
        
        # Permission issues
        if any(kw in error_str for kw in ["permission denied", "access denied", "unauthorized", "forbidden", "not allowed"]):
            return (
                BoundaryCategory.PERMISSION,
                f"Tool '{tool_name}' requires elevated permissions. Verify access rights before use."
            )
        
        # Device issues (ADB, etc.)
        if any(kw in error_str for kw in ["adb", "device not found", "no devices", "offline", "not connected"]):
            return (
                BoundaryCategory.DEVICE,
                f"Tool '{tool_name}' failed due to device issues. Ensure device is connected and authorized."
            )
        
        # Resource issues
        if any(kw in error_str for kw in ["out of memory", "disk full", "quota exceeded", "resource", "no space"]):
            return (
                BoundaryCategory.RESOURCE,
                f"Tool '{tool_name}' failed due to resource constraints. Free up resources before retry."
            )
        
        # Tool-specific issues
        if any(kw in error_str for kw in ["not found", "not installed", "command not found", "no such file"]):
            return (
                BoundaryCategory.TOOL,
                f"Tool '{tool_name}' or its dependencies may not be properly installed."
            )
        
        return (BoundaryCategory.UNKNOWN, "")
    
    def get_all_boundaries(self) -> List[str]:
        """
        Get all current capability boundaries (static + dynamic).
        
        Expired dynamic boundaries are automatically pruned.
        """
        # Prune expired boundaries
        self._prune_expired()
        
        # Combine static and dynamic
        dynamic_descriptions = [b.description for b in self._boundaries.values()]
        return self._static_boundaries + dynamic_descriptions
    
    def get_dynamic_boundaries(self) -> List[DynamicBoundary]:
        """Get only the dynamic (learned) boundaries."""
        self._prune_expired()
        return list(self._boundaries.values())
    
    def _prune_expired(self) -> None:
        """Remove expired boundaries."""
        expired_keys = [k for k, v in self._boundaries.items() if v.is_expired]
        for key in expired_keys:
            del self._boundaries[key]
            logger.debug(f"Pruned expired boundary: {key}")
    
    def clear_dynamic(self) -> None:
        """Clear all dynamic boundaries (for testing)."""
        self._boundaries.clear()
    
    def get_stats(self) -> dict:
        """Get statistics about current boundaries."""
        self._prune_expired()
        return {
            "static_count": len(self._static_boundaries),
            "dynamic_count": len(self._boundaries),
            "categories": {
                cat.value: len([b for b in self._boundaries.values() if b.category == cat])
                for cat in BoundaryCategory
                if any(b.category == cat for b in self._boundaries.values())
            }
        }


# Singleton instance
boundary_manager = AdaptiveBoundaryManager()
