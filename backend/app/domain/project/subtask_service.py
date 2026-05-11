"""
Subtask Service for hierarchical task management.

Provides:
- Create parent task with subtasks
- Get task tree structure
- Update task progress with automatic parent update
- Flatten task tree for execution
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.project import ProjectTask
from app.infrastructure.database.sql.database import session_scope
from app.utils.id import gen_uuid
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class SubtaskService:
    """Service for managing hierarchical subtasks."""

    @staticmethod
    async def create_task_with_subtasks(
        project_id: int,
        title: str,
        analysis_id: Optional[str] = None,
        description: str = "",
        priority: str = "medium",
        estimated_hours: int = 0,
        subtasks: list[dict] = None,
        created_by: str = "agent"
    ) -> ProjectTask:
        """
        Create a parent task with optional subtasks.
        
        Args:
            project_id: Project ID
            analysis_id: Analysis ID (can be dummy for direct creation)
            title: Task title
            description: Task description
            priority: high/medium/low
            estimated_hours: Estimated hours
            subtasks: List of subtask dicts [{"title": ..., "description": ..., ...}]
            created_by: Creator identifier
            
        Returns:
            Created parent task with subtasks loaded
        """
        async with session_scope() as session:
            # Create parent task
            parent_task = ProjectTask(
                id=gen_uuid(),
                analysis_id=analysis_id,
                project_id=project_id,
                parent_id=None,  # Root task
                status="pending",
                progress=0,
                task_data={
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "estimated_hours": estimated_hours,
                    "created_by": created_by,
                    "is_parent": True,
                },
                sync_status="pending"
            )
            session.add(parent_task)
            await session.flush()  # Get parent ID

            # Create subtasks if provided
            if subtasks:
                for i, subtask_data in enumerate(subtasks):
                    subtask = ProjectTask(
                        id=gen_uuid(),
                        analysis_id=analysis_id,
                        project_id=project_id,
                        parent_id=parent_task.id,
                        status="pending",
                        progress=0,
                        task_data={
                            "title": subtask_data.get("title", f"Subtask {i+1}"),
                            "description": subtask_data.get("description", ""),
                            "priority": subtask_data.get("priority", priority),
                            "estimated_hours": subtask_data.get("estimated_hours", 0),
                            "order": i,  # Execution order
                            "created_by": created_by,
                        },
                        sync_status="pending"
                    )
                    session.add(subtask)

            # Reload with subtasks
            result = await session.execute(
                select(ProjectTask)
                .where(ProjectTask.id == parent_task.id)
                .options(selectinload(ProjectTask.subtasks))
            )
            return result.scalar_one()

    @staticmethod
    async def get_task_tree(
        task_id: str,
        max_depth: int = 5
    ) -> Optional[dict]:
        """
        Get task tree structure recursively.
        
        Args:
            task_id: Root task ID
            max_depth: Maximum recursion depth
            
        Returns:
            Tree structure dict or None
        """
        async with session_scope() as session:
            result = await session.execute(
                select(ProjectTask)
                .where(ProjectTask.id == task_id)
                .options(selectinload(ProjectTask.subtasks))
            )
            task = result.scalar_one_or_none()
            
            if not task:
                return None
                
            return await SubtaskService._build_tree_recursive(task, max_depth, 0, session)

    @staticmethod
    async def _build_tree_recursive(
        task: ProjectTask,
        max_depth: int,
        current_depth: int,
        session
    ) -> dict:
        """Build tree recursively."""
        tree = {
            "id": task.id,
            "title": task.task_data.get("title", "Untitled"),
            "description": task.task_data.get("description", ""),
            "status": task.status,
            "progress": task.progress,
            "priority": task.task_data.get("priority", "medium"),
            "estimated_hours": task.task_data.get("estimated_hours", 0),
            "is_parent": len(task.subtasks) > 0,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "subtasks": []
        }
        
        if current_depth < max_depth and task.subtasks:
            # Load subtasks with their subtasks
            for subtask in task.subtasks:
                await session.refresh(subtask, ["subtasks"])
                subtree = await SubtaskService._build_tree_recursive(
                    subtask, max_depth, current_depth + 1, session
                )
                tree["subtasks"].append(subtree)
                
        return tree

    @staticmethod
    async def update_task_progress(
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[str] = None
    ) -> bool:
        """
        Update task progress and propagate to parent.
        
        Args:
            task_id: Task ID
            status: pending/in_progress/completed/failed
            progress: 0-100
            result: Execution result/summary
            
        Returns:
            True if updated successfully
        """
        async with session_scope() as session:
            task = await session.get(ProjectTask, task_id)
            if not task:
                logger.error(f"[SubtaskService] Task {task_id} not found")
                return False

            # Update task
            if status:
                task.status = status
                if status == "completed":
                    task.progress = 100
                elif status == "pending":
                    task.progress = 0
                    
            if progress is not None:
                task.progress = max(0, min(100, progress))
                
            if result:
                task.task_data["result"] = result
                
            task.updated_at = utcnow()
            await session.flush()

            # Propagate to parent
            if task.parent_id:
                await SubtaskService._update_parent_progress(task.parent_id, session)
                
            return True

    @staticmethod
    async def _update_parent_progress(parent_id: str, session):
        """Update parent progress based on subtasks."""
        parent = await session.get(ProjectTask, parent_id)
        if not parent:
            return
            
        # Load subtasks
        result = await session.execute(
            select(ProjectTask)
            .where(ProjectTask.parent_id == parent_id)
        )
        subtasks = result.scalars().all()
        
        if not subtasks:
            return
            
        # Calculate weighted progress
        total_hours = sum(s.task_data.get("estimated_hours", 1) for s in subtasks)
        if total_hours == 0:
            total_hours = len(subtasks)
            
        weighted_progress = sum(
            s.progress * (s.task_data.get("estimated_hours", 1) / total_hours)
            for s in subtasks
        )
        
        parent.progress = int(weighted_progress)
        
        # Update parent status
        all_completed = all(s.status == "completed" for s in subtasks)
        any_failed = any(s.status == "failed" for s in subtasks)
        any_in_progress = any(s.status == "in_progress" for s in subtasks)
        
        if all_completed:
            parent.status = "completed"
        elif any_failed:
            parent.status = "failed"
        elif any_in_progress:
            parent.status = "in_progress"
        else:
            parent.status = "pending"
            
        parent.updated_at = utcnow()
        logger.info(f"[SubtaskService] Updated parent {parent_id} progress to {parent.progress}%")

    @staticmethod
    async def get_next_executable_task(project_id: int) -> Optional[dict]:
        """
        Get next task ready for execution.
        Returns first pending subtask or parent task with no subtasks.
        
        Args:
            project_id: Project ID
            
        Returns:
            Task dict or None
        """
        async with session_scope() as session:
            # Get all root tasks for project
            result = await session.execute(
                select(ProjectTask)
                .where(
                    ProjectTask.project_id == project_id,
                    ProjectTask.parent_id.is_(None)
                )
                .order_by(ProjectTask.created_at)
            )
            root_tasks = result.scalars().all()
            
            for root in root_tasks:
                if root.status == "completed":
                    continue
                    
                # Load subtasks
                await session.refresh(root, ["subtasks"])
                
                if not root.subtasks:
                    # Leaf task, can execute
                    if root.status == "pending":
                        return {
                            "id": root.id,
                            "title": root.task_data.get("title", ""),
                            "description": root.task_data.get("description", ""),
                            "is_subtask": False
                        }
                else:
                    # Find first pending subtask
                    for subtask in sorted(root.subtasks, key=lambda x: x.task_data.get("order", 0)):
                        if subtask.status == "pending":
                            return {
                                "id": subtask.id,
                                "title": subtask.task_data.get("title", ""),
                                "description": subtask.task_data.get("description", ""),
                                "parent_title": root.task_data.get("title", ""),
                                "is_subtask": True
                            }
                            
            return None

    @staticmethod
    async def flatten_task_tree(task_id: str) -> list[dict]:
        """
        Flatten task tree to execution list (depth-first).
        
        Args:
            task_id: Root task ID
            
        Returns:
            List of tasks in execution order
        """
        tree = await SubtaskService.get_task_tree(task_id)
        if not tree:
            return []
            
        flat_list = []
        
        def traverse(node, depth=0):
            flat_list.append({
                "id": node["id"],
                "title": node["title"],
                "status": node["status"],
                "progress": node["progress"],
                "depth": depth,
                "estimated_hours": node.get("estimated_hours", 0)
            })
            for child in node.get("subtasks", []):
                traverse(child, depth + 1)
                
        traverse(tree)
        return flat_list


# Global instance
subtask_service = SubtaskService()
