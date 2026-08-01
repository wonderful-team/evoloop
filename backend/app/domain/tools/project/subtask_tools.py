"""
Agent tools for hierarchical subtask management.

These tools allow Agent to:
1. Create complex tasks with subtasks
2. Track task progress
3. Get next executable task
4. Update task completion status
"""

import json
import logging
from app.core.context.manager import ContextManager
from app.core.project.subtask_service import subtask_service
from app.core.tools import evoloop_tool
from app.infrastructure.database import session_scope
from app.models.project import ProjectTask
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


def _get_project_id() -> int:
    """Resolve project ID from context or raise error."""
    # Use standard project ID resolution
    return ContextManager.resolve_project_id(allow_global=True)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.create_task_with_subtasks"
)
async def create_task_with_subtasks(
    title: str,
    description: str = "",
    subtasks_json: str = "[]",
    priority: str = "medium",
    estimated_hours: int = 0
) -> str:
    """
    Create a parent task with subtasks for complex work breakdown.
    
    Use this when the user asks for something that requires multiple steps.
    Break down complex requirements into manageable subtasks.
    
    Args:
        title: Main task title
        description: Task description
        subtasks_json: JSON array of subtasks [{"title": "...", "description": "...", "estimated_hours": n}]
        priority: high/medium/low
        estimated_hours: Total estimated hours
        
    Example:
        title: "实现用户登录功能"
        description: "完整的用户登录模块开发"
        subtasks_json: '[
            {"title": "设计用户表结构", "description": "创建用户表和索引", "estimated_hours": 2},
            {"title": "实现登录API", "description": "POST /api/login", "estimated_hours": 3},
            {"title": "前端登录页面", "description": "登录表单和验证", "estimated_hours": 3}
        ]'
        priority: "high"
        estimated_hours: 8
        
    Returns:
        Success message with task ID and subtask count
    """
    try:
        # Parse subtasks
        subtasks = json.loads(subtasks_json) if subtasks_json else []
        if not isinstance(subtasks, list):
            return "Error: subtasks_json must be a JSON array"
            
        # Get project context
        project_id = _get_project_id()
        
        # Create task with subtasks
        task = await subtask_service.create_task_with_subtasks(
            project_id=project_id,
            analysis_id=f"agent-{gen_uuid()}",
            title=title,
            description=description,
            priority=priority,
            estimated_hours=estimated_hours,
            subtasks=subtasks,
            created_by="agent"
        )
        
        # Track in context
        ctx = ContextManager.current()
        ctx.current_task_id = task.id
        
        # Format response
        subtask_count = len(task.subtasks)
        
        if subtask_count > 0:
            subtask_list = "\n".join([
                f"  {i+1}. {s.task_data.get('title', 'Untitled')}"
                for i, s in enumerate(task.subtasks)
            ])
            return f"""Created task "{title}" with {subtask_count} subtasks

Task ID: {task.id[:8]}

Subtasks:
{subtask_list}

You can track progress by asking "show task tree {task.id[:8]}". 
I've set this as your current active task.""", {"id": task.id, "count": subtask_count}
        else:
            return f"Created task \"{title}\"\n\nTask ID: {task.id[:8]}\n\nI've set this as your current active task.", {"id": task.id}
            
    except json.JSONDecodeError:
        return "Error: subtasks_json is not valid JSON. Format: [{\"title\": \"...\", \"estimated_hours\": n}]"
    except Exception as e:
        logger.error(f"[SubtaskTool] Failed to create task: {e}")
        return f"Error creating task: {str(e)}"


@evoloop_tool(summary_template="evoloop.tool_summary.get_task_tree_summary")
async def get_task_tree_summary(task_id: str) -> str:
    """
    Get hierarchical view of a task and its subtasks with progress.
    
    Use this to check task status and see overall progress.
    
    Args:
        task_id: Task ID (full UUID or first 8 characters)
        
    Example:
        task_id: "abc12345"
        
    Returns:
        Formatted task tree with progress indicators
    """
    try:
        task = await subtask_service.get_task(task_id)
        if not task:
            return f"Error: Task with ID '{task_id}' not found"
        
        # Update current task in context if found
        ctx = ContextManager.current()
        ctx.current_task_id = task.id

        tree = await subtask_service.get_task_tree(task.id)
        
        if not tree:
            return f"Error: Task {task_id} not found"
            
        # Format tree as text
        def format_tree(node, depth=0, is_last=True):
            indent = "  " * depth
            prefix = "└── " if is_last else "├── "
            
            # Progress indicator
            status_map = {
                "completed": "[DONE]",
                "in_progress": "[IN_PROGRESS]",
                "failed": "[FAILED]",
                "pending": "[PENDING]",
            }
            status_icon = status_map.get(node["status"], f"[{node['status'].upper()}]")
                
            line = f"{indent}{prefix}{status_icon} {node['title']} ({node['progress']}%)\n"
            
            children = node.get("subtasks", [])
            for i, child in enumerate(children):
                line += format_tree(child, depth + 1, i == len(children) - 1)
                
            return line
            
        summary = f"""Task Tree: {tree['title']}
Overall Progress: {tree['progress']}%
Status: {tree['status']}

{format_tree(tree, 0, True)}"""
        
        return summary
        
    except Exception as e:
        logger.error(f"[SubtaskTool] Failed to get task tree: {e}")
        return f"Error getting task tree: {str(e)}"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.update_task_completion"
)
async def update_task_completion(
    task_id: str,
    status: str,
    result_summary: str = "",
    progress: int | None = None
) -> str:
    """
    Update task status and progress.
    
    Use this when you complete a task or subtask.
    
    Args:
        task_id: Task ID or "current" to use active task
        status: pending/in_progress/completed/failed
        result_summary: Brief summary of what was done
        progress: Progress percentage (0-100), auto-calculated if not provided
        
    Example:
        task_id: "abc12345"
        status: "completed"
        result_summary: "Implemented user authentication with JWT tokens"
        
    Returns:
        Success message with updated progress
    """
    try:
        ctx = ContextManager.current()
        
        # Handle "current" keyword
        if task_id == "current":
            if not ctx.current_task_id:
                return "Error: No current task found in context. Please specify a task_id."
            task_id = ctx.current_task_id
        
        # Resolve task (handles partial ID)
        task = await subtask_service.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"
        
        task_id = task.id
        ctx.current_task_id = task_id
        
        # Auto-set progress based on status
        if progress is None:
            if status == "completed":
                progress = 100
            elif status == "pending":
                progress = 0
                
        success = await subtask_service.update_task_progress(
            task_id=task_id,
            status=status,
            progress=progress,
            result=result_summary
        )
        
        if not success:
            return f"Error: Failed to update task {task_id[:8]}"
            
        # Get updated tree to show progress
        task_tree = await subtask_service.get_task_tree(task_id)
        if not task_tree:
            return f"Updated task to {status} ({progress}%)"

        # Resolve parent ID to show context
        async with session_scope() as session:
            task_obj = await session.get(ProjectTask, task_id)
            parent_id = task_obj.parent_id if task_obj else None

        if parent_id:
            parent_tree = await subtask_service.get_task_tree(parent_id)
            return (
                f"Updated subtask \"{task_tree['title']}\" to {status} ({progress}%)\n"
                f"Parent task \"{parent_tree['title']}\" overall progress: {parent_tree['progress']}%"
            )
        elif task_tree.get("subtasks"):
            return f"Updated parent task \"{task_tree['title']}\" to {status} ({progress}%)"
        else:
            return f"Updated task to {status} ({progress}%)"
            
    except Exception as e:
        logger.error(f"[SubtaskTool] Failed to update task: {e}")
        return f"Error updating task: {str(e)}"


@evoloop_tool(summary_template="evoloop.tool_summary.get_next_executable_task")
async def get_next_executable_task() -> str:
    """
    Get the next task ready for execution.
    
    Use this to find what to work on next.
    Returns the first pending subtask in order.
    
    Returns:
        Task details or message if no pending tasks
    """
    try:
        project_id = _get_project_id()
        
        task = await subtask_service.get_next_executable_task(project_id)
        
        if not task:
            return "No pending tasks! All tasks are completed or in progress."
            
        # Track this task as current
        ctx = ContextManager.current()
        ctx.current_task_id = task["id"]

        prefix = "└── " if task.get("is_subtask") else ""
        parent_info = f"\nPart of: {task['parent_title']}" if task.get("parent_title") else ""
        
        return f"""Next Task to Execute:

{prefix}{task['title']}

ID: {task['id'][:8]}
Description: {task['description'] or 'No description'}{parent_info}

I've set this as your current task. You can use update_task_completion without an ID."""
        
    except Exception as e:
        logger.error(f"[SubtaskTool] Failed to get next task: {e}")
        return f"Error getting next task: {str(e)}"


@evoloop_tool(summary_template="evoloop.tool_summary.list_project_tasks")
async def list_project_tasks(
    status_filter: str = "all",
    limit: int = 20
) -> str:
    """
    List root tasks for the current project.
    
    Use this to get an overview of project tasks.
    
    Args:
        status_filter: all/pending/in_progress/completed/failed
        limit: Maximum number of tasks to show
        
    Returns:
        Formatted task list
    """
    try:
        project_id = _get_project_id()
        
        tasks = await subtask_service.list_project_tasks(
            project_id=project_id,
            status_filter=status_filter,
            limit=limit
        )
        
        if not tasks:
            return "No tasks found in this project.", {"count": 0}
            
        lines = [f"Project Tasks ({len(tasks)} total):\n"]
        
        for t in tasks:
            status_label = {
                "completed": "[DONE]",
                "in_progress": "[IN_PROGRESS]",
                "failed": "[FAILED]",
            }.get(t.status, "[PENDING]")
                
            title = t.task_data.get("title", "Untitled")
            progress = t.progress
            
            lines.append(f"{status_label} {title} ({progress}%) - ID: {t.id[:8]}")
            
        lines.append(f"\nUse get_task_tree_summary with task ID to see subtasks.")
        
        return "\n".join(lines), {"count": len(tasks)}
            
    except Exception as e:
        logger.error(f"[SubtaskTool] Failed to list tasks: {e}")
        return f"Error listing tasks: {str(e)}"
