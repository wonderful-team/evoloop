"""
Tool Output Memory - Manages forgotten tool outputs for context management.

Provides safe forgetting mechanism with:
- Audit logging
- Safety window enforcement (can only forget outputs older than N steps)
- Soft forgetting (keep summary)
- Recall capability
"""
import logging
import time

from app.core.engine.state import AgentState
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.memory.schemas import ForgottenRecord, AuditEntry

logger = logging.getLogger(__name__)


class ToolOutputMemory:
    """
    Manages the "forgetting" status of tool outputs.

    Design principles:
    1. Soft forgetting: Always keep a summary (never truly delete)
    2. Safety window: Can only forget outputs older than N steps
    3. Audit trail: All operations logged for debugging
    4. Recallable: Forgotten outputs can be referenced/reloaded

    Storage: Serialized into blackboard.metadata["tool_memory"]
    """

    def __init__(self):
        self.forgotten: dict[str, ForgottenRecord] = {}
        self.audit_log: list[AuditEntry] = []

    def can_forget(
        self,
        tool_call_id: str,
        current_step: int,
        safety_window: int = 5,
    ) -> tuple[bool, str]:
        """
        Check if a tool output can be safely forgotten.

        Args:
            tool_call_id: The tool call ID to check
            current_step: Current message step/index
            safety_window: Minimum steps ago the tool must have been called

        Returns:
            (can_forget, reason)
        """
        # Check if already forgotten
        if tool_call_id in self.forgotten:
            return False, "Already forgotten"

        # Note: The actual step index check should be done by the caller
        # who knows the tool's position in the message history
        return True, "OK"

    def mark_forgotten(
        self,
        tool_call_id: str,
        tool_name: str,
        summary: str,
        original_length: int,
        reason: str,
        step_index: int,
    ) -> ForgottenRecord:
        """
        Mark a tool output as forgotten.

        Args:
            tool_call_id: Unique tool call identifier
            tool_name: Name of the tool
            summary: Brief summary to keep (required, cannot be empty)
            original_length: Original content length in characters
            reason: Why this is being forgotten
            step_index: Message index for tracking

        Returns:
            The created ForgottenRecord

        Raises:
            ValueError: If summary is empty or tool already forgotten
        """
        if not summary or not summary.strip():
            raise ValueError("Summary cannot be empty when forgetting a tool output")

        if tool_call_id in self.forgotten:
            raise ValueError(f"Tool output {tool_call_id} is already forgotten")

        record = ForgottenRecord(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            summary=summary.strip(),
            original_length=original_length,
            forgotten_at=time.time(),
            reason=reason.strip() if reason else "No reason provided",
            step_index=step_index,
        )

        self.forgotten[tool_call_id] = record

        # Log to audit
        self.audit_log.append(AuditEntry(
            action="forget",
            tool_call_id=tool_call_id,
            timestamp=time.time(),
            reason=reason,
            success=True,
            details=f"Original length: {original_length}, Summary: {summary[:100]}...",
        ))

        logger.info(f"[ToolOutputMemory] Forgot {tool_name} ({tool_call_id}): {reason}")
        return record

    def get_summary(self, tool_call_id: str) -> str | None:
        """
        Get the summary of a forgotten tool output.

        Returns:
            Summary string if forgotten, None otherwise
        """
        record = self.forgotten.get(tool_call_id)
        if record:
            return record.summary
        return None

    def is_forgotten(self, tool_call_id: str) -> bool:
        """Check if a tool output has been forgotten."""
        return tool_call_id in self.forgotten

    def get_forgotten_info(self, tool_call_id: str) -> ForgottenRecord | None:
        """Get full forgotten record including metadata."""
        return self.forgotten.get(tool_call_id)

    def recall(
        self,
        tool_call_id: str,
        full_content: str | None = None,
    ) -> tuple[bool, str]:
        """
        Mark a forgotten tool as "recalled" (needed again).

        Note: This doesn't actually restore the content to messages - that
        must be done by the caller (e.g., by fetching from DB). This just
        updates the memory state and audit log.

        Args:
            tool_call_id: The tool to recall
            full_content: If provided, the recalled content (for logging)

        Returns:
            (success, message)
        """
        record = self.forgotten.get(tool_call_id)
        if not record:
            self.audit_log.append(AuditEntry(
                action="recall",
                tool_call_id=tool_call_id,
                timestamp=time.time(),
                reason="Attempted recall",
                success=False,
                details="Tool was not forgotten",
            ))
            return False, "Tool output was not forgotten"

        # Note: We don't remove from forgotten - we just mark it as recalled
        # The actual restoration is handled by the recall_tool_output tool
        self.audit_log.append(AuditEntry(
            action="recall",
            tool_call_id=tool_call_id,
            timestamp=time.time(),
            reason=f"Recalled {record.tool_name}",
            success=True,
            details=f"Summary was: {record.summary[:100]}...",
        ))

        logger.info(f"[ToolOutputMemory] Recalled {record.tool_name} ({tool_call_id})")
        return True, f"Recalled {record.tool_name}"

    def remove_from_forgotten(self, tool_call_id: str) -> bool:
        """
        Actually remove a tool from forgotten list (restore it).

        This is called after successful recall when the content has been
        restored to the context.
        """
        if tool_call_id in self.forgotten:
            record = self.forgotten.pop(tool_call_id)
            logger.info(f"[ToolOutputMemory] Restored {record.tool_name} ({tool_call_id})")
            return True
        return False

    def list_forgotten(self, limit: int = 20) -> list[ForgottenRecord]:
        """List recently forgotten tool outputs."""
        sorted_records = sorted(
            self.forgotten.values(),
            key=lambda r: r.forgotten_at,
            reverse=True,
        )
        return sorted_records[:limit]

    def get_stats(self) -> dict:
        """Get statistics about forgotten tools."""
        if not self.forgotten:
            return {"count": 0, "total_original_chars": 0}

        total_original = sum(r.original_length for r in self.forgotten.values())
        total_summary = sum(len(r.summary) for r in self.forgotten.values())

        return {
            "count": len(self.forgotten),
            "total_original_chars": total_original,
            "total_summary_chars": total_summary,
            "savings_chars": total_original - total_summary,
            "savings_ratio": (total_original - total_summary) / total_original if total_original > 0 else 0,
        }

    def to_dict(self) -> dict:
        """Serialize to dict for storage in blackboard."""
        return {
            "forgotten": {
                k: {
                    "tool_call_id": v.tool_call_id,
                    "tool_name": v.tool_name,
                    "summary": v.summary,
                    "original_length": v.original_length,
                    "forgotten_at": v.forgotten_at,
                    "reason": v.reason,
                    "step_index": v.step_index,
                }
                for k, v in self.forgotten.items()
            },
            "audit_log": [
                {
                    "action": e.action,
                    "tool_call_id": e.tool_call_id,
                    "timestamp": e.timestamp,
                    "reason": e.reason,
                    "success": e.success,
                    "details": e.details,
                }
                for e in self.audit_log[-100:]  # Keep last 100 entries
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolOutputMemory":
        """Deserialize from dict."""
        memory = cls()

        for k, v in data.get("forgotten", {}).items():
            memory.forgotten[k] = ForgottenRecord(
                tool_call_id=v["tool_call_id"],
                tool_name=v["tool_name"],
                summary=v["summary"],
                original_length=v["original_length"],
                forgotten_at=v["forgotten_at"],
                reason=v["reason"],
                step_index=v["step_index"],
            )

        for e in data.get("audit_log", []):
            memory.audit_log.append(AuditEntry(
                action=e["action"],
                tool_call_id=e["tool_call_id"],
                timestamp=e["timestamp"],
                reason=e["reason"],
                success=e["success"],
                details=e.get("details", ""),
            ))

        return memory


def get_tool_memory_from_state(state: "AgentState") -> ToolOutputMemory:
    """
    Helper to get or create ToolOutputMemory from AgentState.

    Args:
        state: AgentState

    Returns:
        ToolOutputMemory instance
    """
    blackboard = state.blackboard
    metadata = dict(blackboard.metadata) if blackboard and blackboard.metadata else {}
    tool_memory_data = metadata.get("tool_memory")

    if tool_memory_data:
        try:
            return ToolOutputMemory.from_dict(tool_memory_data)
        except Exception as e:
            logger.warning(f"[ToolOutputMemory] Failed to load from state: {e}")

    return ToolOutputMemory()


def save_tool_memory_to_state(state: "AgentState", memory: ToolOutputMemory) -> None:
    """
    Helper to save ToolOutputMemory back to AgentState.
    """
    from app.core.engine.state.blackboard import BlackboardMetadata, BlackboardState
    if not state.blackboard:
        state.blackboard = BlackboardState()

    if not state.blackboard.metadata:
        state.blackboard.metadata = BlackboardMetadata()

    state.blackboard.metadata.tool_memory = memory.to_dict()
