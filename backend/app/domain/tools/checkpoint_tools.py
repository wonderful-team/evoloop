"""
Checkpoint Tools
================

User-facing tools for checkpoint management.
"""

from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool
from app.core.checkpoint.manager import checkpoint_manager


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.create_checkpoint",
    name_map={"zh": "创建检查点", "en": "Create Checkpoint"}
)
async def create_checkpoint(
    name: str,
    file_paths: list[str],
    description: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Create a named checkpoint (snapshot) of specified files for easy rollback.
    
    Use this when:
    - Before making risky changes
    - Before refactoring multiple files
    - To save a working state before experimentation
    
    Args:
        name: A descriptive name for this checkpoint (e.g., "Before refactor", "Working auth")
        file_paths: List of file paths to include in the snapshot
        description: Optional longer description of what's in this checkpoint
    
    Returns:
        Confirmation with checkpoint ID and summary
    
    Example:
        create_checkpoint(
            name="Before JWT refactor",
            file_paths=["src/auth.py", "src/middleware.py"],
            description="Working state before attempting JWT authentication"
        )
    """
    if not name or not file_paths:
        return "Error: 'name' and 'file_paths' are required."
    
    # Get context
    ctx = ContextManager.current()
    thread_id = ctx.thread_id or "default"
    project_id = ctx.project_id
    
    try:
        checkpoint = await checkpoint_manager.create_file_checkpoint(
            thread_id=thread_id,
            name=name,
            file_paths=file_paths,
            description=description,
            project_id=project_id,
            created_by="manual"
        )
        
        total_size = sum(f.file_size for f in checkpoint.files)
        total_lines = sum(f.line_count for f in checkpoint.files)
        
        return (
            f"✅ Created checkpoint #{checkpoint.id}: '{name}'\n"
            f"   Files: {len(checkpoint.files)}\n"
            f"   Size: {total_size:,} bytes\n"
            f"   Lines: {total_lines:,}\n"
            f"\n💡 To rollback later:\n"
            f"   rollback_checkpoint(checkpoint_id={checkpoint.id})"
        )
        
    except Exception as e:
        return f"❌ Failed to create checkpoint: {e}"


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.list_checkpoints",
    name_map={"zh": "列出检查点", "en": "List Checkpoints"}
)
async def list_checkpoints(
    include_auto: bool = False,
    limit: int = 10,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    List available checkpoints for the current conversation.
    
    Args:
        include_auto: Whether to include auto-created checkpoints (default: False)
        limit: Maximum number to show (default: 10)
    
    Returns:
        Formatted list of checkpoints with IDs, names, and file counts
    
    Example:
        list_checkpoints()  # Show manual checkpoints
        list_checkpoints(include_auto=True)  # Include auto-created ones
    """
    ctx = ContextManager.current()
    thread_id = ctx.thread_id or "default"
    
    try:
        checkpoints = await checkpoint_manager.list_checkpoints(
            thread_id=thread_id,
            include_auto=include_auto,
            limit=limit
        )
        
        if not checkpoints:
            return "No checkpoints found. Create one with create_checkpoint()."
        
        lines = [f"📋 Checkpoints ({len(checkpoints)} total):\n"]
        
        for cp in checkpoints:
            auto_tag = " [AUTO]" if cp.created_by == "auto" else ""
            desc = f" - {cp.description[:50]}..." if cp.description else ""
            
            lines.append(
                f"  #{cp.id}: {cp.name}{auto_tag}"
            )
            lines.append(
                f"      Files: {len(cp.files)} | "
                f"Created: {cp.created_at.strftime('%Y-%m-%d %H:%M')}{desc}"
            )
        
        lines.append(f"\n💡 To rollback: rollback_checkpoint(checkpoint_id=<id>)")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ Failed to list checkpoints: {e}"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.rollback_checkpoint",
    name_map={"zh": "回滚检查点", "en": "Rollback Checkpoint"}
)
async def rollback_checkpoint(
    checkpoint_id: int,
    dry_run: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Roll back files to a saved checkpoint state.
    
    IMPORTANT: By default, this shows a preview (dry_run=True). 
    Set dry_run=False to actually apply the changes.
    
    Args:
        checkpoint_id: The checkpoint ID to restore (from list_checkpoints)
        dry_run: If True, preview changes without applying (default: True)
    
    Returns:
        Preview or confirmation of restored files
    
    Example:
        # First, preview what will change
        rollback_checkpoint(checkpoint_id=5)
        
        # Then, if satisfied, actually apply
        rollback_checkpoint(checkpoint_id=5, dry_run=False)
    """
    try:
        checkpoint = await checkpoint_manager.get_checkpoint(checkpoint_id)
        if not checkpoint:
            return f"❌ Checkpoint #{checkpoint_id} not found."
        
        results = await checkpoint_manager.rollback_to_checkpoint(
            checkpoint_id=checkpoint_id,
            dry_run=dry_run
        )
        
        lines = []
        
        if dry_run:
            lines.append(f"📋 Preview: Rollback to checkpoint #{checkpoint_id} '{checkpoint.name}'\n")
        else:
            lines.append(f"✅ Rolled back to checkpoint #{checkpoint_id} '{checkpoint.name}'\n")
        
        # Restored files
        if results["restored"]:
            lines.append(f"📝 Files to restore ({len(results['restored'])}):")
            for f in results["restored"]:
                lines.append(f"  + {f['path']} ({f['lines']} lines)")
        
        # Skipped files
        if results["skipped"]:
            lines.append(f"\n⏭️  Unchanged ({len(results['skipped'])}):")
            for f in results["skipped"]:
                lines.append(f"  = {f['path']}")
        
        # Failed files
        if results["failed"]:
            lines.append(f"\n❌ Failed ({len(results['failed'])}):")
            for f in results["failed"]:
                lines.append(f"  ✗ {f['path']}: {f['error']}")
        
        if dry_run:
            lines.append(f"\n💡 To apply this rollback, run:\n")
            lines.append(f"   rollback_checkpoint(checkpoint_id={checkpoint_id}, dry_run=False)")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ Failed to rollback: {e}"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.delete_checkpoint",
    name_map={"zh": "删除检查点", "en": "Delete Checkpoint"}
)
async def delete_checkpoint(
    checkpoint_id: int,
    confirm: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Delete a checkpoint permanently.
    
    Args:
        checkpoint_id: The checkpoint to delete
        confirm: Must be True to actually delete
    
    Returns:
        Confirmation or error message
    """
    if not confirm:
        return (
            f"⚠️ This will permanently delete checkpoint #{checkpoint_id}.\n"
            f"To confirm, run: delete_checkpoint(checkpoint_id={checkpoint_id}, confirm=True)"
        )
    
    success = await checkpoint_manager.delete_checkpoint(checkpoint_id)
    
    if success:
        return f"✅ Deleted checkpoint #{checkpoint_id}"
    else:
        return f"❌ Checkpoint #{checkpoint_id} not found"
