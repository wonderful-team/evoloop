"""
Pre-compact hook handler — saves checkpoint state before context compression.
"""

import logging
from datetime import datetime

import yaml
from langchain_core.messages import BaseMessage

from app.core.engine.hooks.core import HookContext, HookResult
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

logger = logging.getLogger(__name__)


async def pre_compact_save_state(context: HookContext) -> HookResult:
    """
    CRITICAL: Save state before context compression.

    This is the most important hook - it prevents loss of critical
    information when the context window fills up.

    Saves:
    - Task progress
    - Key decisions made
    - Remaining work
    - Important context
    """
    start_time = datetime.utcnow()
    logger.info(f"[PreCompact] 🔄 Starting checkpoint save for thread={context.thread_id}")

    # Use provided memory_manager from context (injected via container)
    mm = context.memory_manager
    if mm is None:
        # Fallback to singleton container if not provided in context
        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            logger.debug("[PreCompact] Initializing MemoryLifespanManager...")
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        mm = container.memory_manager
        logger.debug("[PreCompact] Got memory_manager from singleton container")

    try:
        # Extract critical information from messages
        extract_start = datetime.utcnow()
        task_progress = _extract_task_progress(context.messages)
        key_decisions = _extract_decisions(context.messages)
        extract_elapsed = (datetime.utcnow() - extract_start).total_seconds()
        logger.debug(f"[PreCompact] Extracted task_progress ({len(task_progress)} chars) and {len(key_decisions)} decisions in {extract_elapsed:.3f}s")

        # Check for duplicate checkpoint (same thread_id + same task_progress in last 5 minutes)
        duplicate_check_start = datetime.utcnow()
        existing_checkpoints = await mm.list_memories(type_filter=MemoryType.PROJECT)

        # Look for recent checkpoint with same task progress
        recent_duplicate = None
        for cp_summary in existing_checkpoints:
            if cp_summary.id.startswith(f"checkpoint_{context.thread_id}"):
                # Load full entry to check content
                cp_entry = await mm.get_memory(cp_summary.id)
                if cp_entry:
                    try:
                        cp_data = yaml.safe_load(cp_entry.content)
                        if cp_data.get("task_progress") == task_progress:
                            # Check if within 5 minutes
                            cp_time = datetime.fromisoformat(cp_data.get("timestamp", "2000-01-01"))
                            if (datetime.utcnow() - cp_time).total_seconds() < 300:  # 5 minutes
                                recent_duplicate = cp_entry
                                logger.warning(f"[PreCompact] ⚠️ Found duplicate checkpoint from {cp_time.isoformat()}: {cp_entry.id}")
                                break
                    except Exception as e:
                        logger.debug(f"[PreCompact] Failed to parse existing checkpoint {cp_summary.id}: {e}")

        duplicate_check_elapsed = (datetime.utcnow() - duplicate_check_start).total_seconds()
        logger.debug(f"[PreCompact] Duplicate check: scanned {len(existing_checkpoints)} entries in {duplicate_check_elapsed:.3f}s")

        if recent_duplicate:
            logger.info(f"[PreCompact] ⏭️ Skipping duplicate checkpoint for thread={context.thread_id}")
            return HookResult(
                success=True,
                data={"checkpoint": None, "skipped": True, "reason": "duplicate_within_5min"},
            )

        # Create checkpoint data
        checkpoint = {
            "timestamp": datetime.utcnow().isoformat(),
            "thread_id": context.thread_id,
            "message_count": len(context.messages),
            "task_progress": task_progress,
            "key_decisions": key_decisions,
            "remaining_work": getattr(context.blackboard, "remaining_work", None) if context.blackboard else None,
            "current_goal": getattr(context.blackboard, "current_goal", None) if context.blackboard else None,
            "compact_trigger": context.compact_trigger or "auto",
        }
        logger.debug(f"[PreCompact] Checkpoint data: {len(context.messages)} messages, trigger={checkpoint['compact_trigger']}")

        # Save to memory (ensuring human-readable Unicode)
        save_start = datetime.utcnow()
        
        # Extract source_message_id from last message
        source_message_id = None
        if context.messages:
            last_msg = context.messages[-1]
            source_message_id = getattr(last_msg, "id", None) or last_msg.additional_kwargs.get("message_id")

        memory_entry = MemoryEntry(
            id=f"checkpoint_{context.thread_id}_{int(datetime.utcnow().timestamp())}",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.PRIVATE,
            title=f"Context Checkpoint - {checkpoint['task_progress'][:50]}...",
            description=f"Auto-saved before context compaction ({checkpoint['compact_trigger']})",
            content=yaml.safe_dump(checkpoint, allow_unicode=True, default_flow_style=False, sort_keys=False),
            user_id=context.user_id,
            project_id=context.project_id,
            source_message_id=source_message_id,
            run_id=context.run_id,
            tags=["checkpoint", "pre-compact"],
        )

        await mm.save_memory(memory_entry)
        save_elapsed = (datetime.utcnow() - save_start).total_seconds()

        total_elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"[PreCompact] ✅ Checkpoint saved: {memory_entry.id} in {total_elapsed:.3f}s (save: {save_elapsed:.3f}s)")

        # Create summary for context injection
        summary = f"""
[Context Compaction Checkpoint]
Task: {checkpoint['task_progress'][:100]}
Decisions: {len(checkpoint['key_decisions'])} key decisions made
Remaining: {checkpoint['remaining_work'] or 'Unknown'}
"""

        return HookResult(
            success=True,
            data={"checkpoint": checkpoint, "summary": summary, "checkpoint_id": memory_entry.id},
        )

    except Exception as e:
        total_elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"[PreCompact] ❌ Failed to save state after {total_elapsed:.3f}s: {e}", exc_info=True)
        return HookResult(success=False, error=e)


def _extract_task_progress(messages: list[BaseMessage]) -> str:
    """Extract current task progress from messages."""
    if not messages:
        return "No progress recorded"

    # Look for the most recent human message
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            return str(msg.content)[:200]

    return "Unknown task"


def _extract_decisions(messages: list[BaseMessage]) -> list[str]:
    """Extract key decisions from messages."""
    decisions = []

    for msg in messages:
        if hasattr(msg, 'type') and msg.type == 'ai':
            content = str(msg.content).lower()
            # Look for decision indicators
            if any(keyword in content for keyword in ['decided', 'decision', 'choose', 'selected', 'we will']):
                decisions.append(str(msg.content)[:150])

    return decisions[-5:]  # Last 5 decisions
