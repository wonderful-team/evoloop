"""
Checkpoint Tools
================

User-facing tools for checkpoint management.
"""

import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.checkpoint.manager import checkpoint_manager
from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool
from app.utils import SystemToolsFormatter

logger = logging.getLogger(__name__)


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
    
    # Validate all file paths are within working directory
    from app.domain.tools.files.utils import resolve_and_validate_path
    validated_paths = []
    for fp in file_paths:
        try:
            validated = await resolve_and_validate_path(fp, config)
            validated_paths.append(validated)
        except ValueError as e:
            return f"Error: Invalid file path '{fp}': {e}"
    
    # Get context
    ctx = ContextManager.current()
    thread_id = ctx.thread_id or "default"
    project_id = ctx.project_id
    
    try:
        checkpoint = await checkpoint_manager.create_checkpoint(
            thread_id=thread_id,
            name=name,
            file_paths=validated_paths,
            description=description,
            project_id=project_id,
            created_by="manual"
        )
        
        total_size = sum(f.file_size for f in checkpoint.files)
        total_lines = sum(f.line_count for f in checkpoint.files)
        
        try:
            return SystemToolsFormatter.checkpoint_creation(checkpoint, total_size, total_lines)
        except Exception as e:
            logger.error(f"Failed to render checkpoint creation: {e}")
            return f"Created checkpoint #{checkpoint.id}: '{name}'"
        
    except Exception as e:
        return f"Failed to create checkpoint: {e}"


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
        
        try:
            return SystemToolsFormatter.checkpoints(checkpoints)
        except Exception as e:
            logger.error(f"Failed to render checkpoints list: {e}")
            return "Error listing checkpoints."
        
    except Exception as e:
        return f"Failed to list checkpoints: {e}"


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
            return f"Checkpoint #{checkpoint_id} not found."
        
        results = await checkpoint_manager.rollback_to_checkpoint(
            checkpoint_id=checkpoint_id,
            dry_run=dry_run
        )
        
        try:
            if dry_run:
                return SystemToolsFormatter.rollback_preview(checkpoint_id, checkpoint.name)
            else:
                return SystemToolsFormatter.signals([f"Rolled back to checkpoint #{checkpoint_id} '{checkpoint.name}'"])
        except Exception as e:
            logger.error(f"Failed to render rollback report: {e}")
            return f"Rollback to #{checkpoint_id} complete."
        
    except Exception as e:
        return f"Failed to rollback: {e}"


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
            f"WARNING: This will permanently delete checkpoint #{checkpoint_id}.\n"
            f"To confirm, run: delete_checkpoint(checkpoint_id={checkpoint_id}, confirm=True)"
        )
    
    success = await checkpoint_manager.delete_checkpoint(checkpoint_id)
    
    if success:
        return f"Deleted checkpoint #{checkpoint_id}"
    else:
        return f"Checkpoint #{checkpoint_id} not found"
