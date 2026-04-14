"""
Checkpoint Manager
==================

Manages file checkpoints for easy rollback and recovery.
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc, select, delete
from sqlalchemy.orm import joinedload

from app.infrastructure.database.sql.database import session_scope
from app.models.checkpoint import FileCheckpoint, FileCheckpointSnapshot
from pydantic import BaseModel
from app.infrastructure.pydantic_base import DynamicBaseModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CheckpointRollbackFileResult(DynamicBaseModel):
    path: str
    size: int | None = None
    lines: int | None = None
    error: str | None = None


class CheckpointRollbackSkipped(BaseModel):
    path: str
    reason: str


class CheckpointRollbackResult(DynamicBaseModel):
    checkpoint_id: int
    checkpoint_name: str
    dry_run: bool
    restored: list[CheckpointRollbackFileResult]
    failed: list[CheckpointRollbackFileResult]
    skipped: list[CheckpointRollbackSkipped]


class CheckpointManager:
    """
    Manages creation, listing, and restoration of file checkpoints.
    """
    
    # Configuration
    MAX_CHECKPOINTS_PER_THREAD = 50
    MAX_CHECKPOINT_AGE_DAYS = 30
    AUTO_CHECKPOINT_FILE_THRESHOLD = 3
    
    async def create_checkpoint(
        self,
        thread_id: str,
        name: str,
        file_paths: list[str],
        description: str | None = None,
        project_id: int | None = None,
        created_by: str = "manual",
        source_message_id: str | None = None
    ) -> FileCheckpoint:
        """Create a new checkpoint by snapshotting specified files."""
        checkpoint_files = []
        
        for path in file_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                file_size = len(content.encode('utf-8'))
                line_count = content.count('\n') + 1
                
                cp_file = FileCheckpointSnapshot(
                    file_path=path,
                    content=content,
                    content_hash=content_hash,
                    file_size=file_size,
                    line_count=line_count
                )
                checkpoint_files.append(cp_file)
                
            except Exception as e:
                logger.warning(f"Failed to read file for checkpoint: {path} - {e}")
        
        if not checkpoint_files:
            raise ValueError("No files could be read for checkpoint")
        
        async with session_scope() as session:
            checkpoint = FileCheckpoint(
                name=name,
                description=description,
                thread_id=thread_id,
                project_id=project_id,
                created_by=created_by,
                source_message_id=source_message_id
            )
            checkpoint.files = checkpoint_files
            
            session.add(checkpoint)
            await session.flush()
            
            logger.info(
                f"Created checkpoint {checkpoint.id} '{name}' with {len(checkpoint_files)} files"
            )
            
            if created_by == "auto":
                await self._cleanup_old_checkpoints(session, thread_id)
            
            return checkpoint
    
    async def list_checkpoints(
        self,
        thread_id: str | None = None,
        project_id: int | None = None,
        limit: int = 20,
        include_auto: bool = True
    ) -> list[FileCheckpoint]:
        """List checkpoints for a thread or project."""
        async with session_scope() as session:
            query = select(FileCheckpoint).options(joinedload(FileCheckpoint.files))
            
            if thread_id:
                query = query.where(FileCheckpoint.thread_id == thread_id)
            if project_id:
                query = query.where(FileCheckpoint.project_id == project_id)
            if not include_auto:
                query = query.where(FileCheckpoint.created_by == "manual")
            
            query = query.order_by(desc(FileCheckpoint.created_at)).limit(limit)
            
            result = await session.execute(query)
            return list(result.scalars().unique())
    
    async def get_checkpoint(self, checkpoint_id: int) -> FileCheckpoint | None:
        """Get a specific checkpoint by ID."""
        async with session_scope() as session:
            result = await session.execute(
                select(FileCheckpoint)
                .options(joinedload(FileCheckpoint.files))
                .where(FileCheckpoint.id == checkpoint_id)
            )
            return result.scalar_one_or_none()
    
    async def rollback_to_checkpoint(
        self,
        checkpoint_id: int,
        dry_run: bool = False
    ) -> CheckpointRollbackResult:
        """Roll back files to a checkpoint state."""
        checkpoint = await self.get_checkpoint(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        
        results = CheckpointRollbackResult(
            checkpoint_id=checkpoint_id,
            checkpoint_name=checkpoint.name,
            dry_run=dry_run,
            restored=[],
            failed=[],
            skipped=[]
        )
        
        for cp_file in checkpoint.files:
            path = cp_file.file_path
            
            try:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                    current_hash = hashlib.sha256(current_content.encode('utf-8')).hexdigest()
                    
                    if current_hash == cp_file.content_hash:
                        results.skipped.append(CheckpointRollbackSkipped(path=path, reason="unchanged"))
                        continue
                        
                except FileNotFoundError:
                    current_content = None
                
                if not dry_run:
                    from app.utils.path import ensure_dir
                    ensure_dir(os.path.dirname(path))
                    
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(cp_file.content)
                    
                    logger.info(f"Restored file from checkpoint {checkpoint_id}: {path}")
                
                results.restored.append(CheckpointRollbackFileResult(
                    path=path,
                    size=cp_file.file_size,
                    lines=cp_file.line_count
                ))
                
            except Exception as e:
                logger.error(f"Failed to restore file: {path} - {e}")
                results.failed.append(CheckpointRollbackFileResult(path=path, error=str(e)))
        
        return results
    
    async def delete_checkpoint(self, checkpoint_id: int) -> bool:
        """Delete a checkpoint."""
        async with session_scope() as session:
            result = await session.execute(
                select(FileCheckpoint).where(FileCheckpoint.id == checkpoint_id)
            )
            checkpoint = result.scalar_one_or_none()
            
            if not checkpoint:
                return False
            
            await session.delete(checkpoint)
            logger.info(f"Deleted checkpoint {checkpoint_id}")
            return True
    
    async def should_auto_checkpoint(self, thread_id: str, pending_file_count: int) -> bool:
        """Determine if we should auto-create a checkpoint."""
        if pending_file_count >= self.AUTO_CHECKPOINT_FILE_THRESHOLD:
            return True
        
        async with session_scope() as session:
            recent = await session.execute(
                select(FileCheckpoint)
                .where(FileCheckpoint.thread_id == thread_id)
                .where(FileCheckpoint.created_by == "auto")
                .where(FileCheckpoint.created_at > datetime.utcnow() - timedelta(minutes=5))
                .limit(1)
            )
            if recent.scalar_one_or_none():
                return False
        
        return False
    
    async def _cleanup_old_checkpoints(self, session, thread_id: str) -> None:
        """Auto-delete old checkpoints."""
        cutoff = datetime.utcnow() - timedelta(days=self.MAX_CHECKPOINT_AGE_DAYS)
        
        old_stmt = delete(FileCheckpoint).where(
            FileCheckpoint.thread_id == thread_id
        ).where(
            FileCheckpoint.created_at < cutoff
        ).where(
            FileCheckpoint.created_by == "auto"
        )
        
        result = await session.execute(old_stmt)
        if result.rowcount:
            logger.info(f"Cleaned up {result.rowcount} old checkpoints")
        
        count_stmt = select(FileCheckpoint.id).where(
            FileCheckpoint.thread_id == thread_id
        ).where(
            FileCheckpoint.created_by == "auto"
        ).order_by(desc(FileCheckpoint.created_at)).offset(
            self.MAX_CHECKPOINTS_PER_THREAD
        )
        
        result = await session.execute(count_stmt)
        excess_ids = [r[0] for r in result.all()]
        
        if excess_ids:
            delete_stmt = delete(FileCheckpoint).where(FileCheckpoint.id.in_(excess_ids))
            result = await session.execute(delete_stmt)
            logger.info(f"Cleaned up {result.rowcount} excess checkpoints")


# Singleton
checkpoint_manager = CheckpointManager()
