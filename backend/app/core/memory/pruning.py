"""
Memory Pruning Service - The "Forget" Logic
Handles semantic cleanup of redundant, stale, or fulfilled memories.
"""
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from app.core.llm import InternalLLMService
from app.core.memory.models import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


class MemoryPruningService:
    """
    Service for identifying and removing memories that are no longer valuable.
    
    Strategies:
    1. Redundancy: If a memory is covered by static docs (README, Norms).
    2. Staleness: If a memory is contradicted by newer code/memories.
    3. Fulfillment: If a TODO task is now marked as complete.
    """

    def __init__(self, storage, project_context=None, todo_service=None):
        self.storage = storage
        self.project_context = project_context
        self.todo_service = todo_service

    async def run_pruning_cycle(self, project_id: Optional[int] = None) -> List[dict]:
        """
        Run a full pruning cycle and return a detailed audit log.
        """
        audit_log = []
        
        # 1. Fetch search results (lightweight)
        results = await self.storage.list_all()
        
        # 2. Fetch full entries for evaluation (Optimized Batch Loading)
        res_ids = [res.id for res in results]
        memory_map = await self.storage.get_multi(res_ids)
        
        memories = []
        for res_id in res_ids:
            entry = memory_map.get(res_id)
            if entry:
                if project_id and entry.project_id != project_id:
                    continue
                memories.append(entry)

        if not memories:
            return []

        # 2. Strategy: Task Fulfillment (Simple & Data-driven)
        if self.todo_service:
            todo_logs = await self._prune_fulfilled_tasks(memories, project_id)
            audit_log.extend(todo_logs)

        # 3. Strategy: Consolidation (Merging related memories)
        # We consolidate every N sessions or when memory grows
        consolidator = MemoryConsolidator(self.storage)
        consolidation_logs = await consolidator.consolidate(memories, project_id)
        audit_log.extend(consolidation_logs)

        # 4. Strategy: Redundancy & Staleness (LLM-assisted)
        if self.project_context:
            # Refresh memories list after consolidation
            updated_memories = [m for m in memories if m.id not in [l['id'] for l in audit_log if l['action'] == 'DELETED']]
            semantic_logs = await self._prune_semantically(updated_memories, project_id)
            audit_log.extend(semantic_logs)

        return audit_log

    async def _prune_fulfilled_tasks(self, memories: List[MemoryEntry], project_id: Optional[int]) -> List[dict]:
        """Prune memories that reference already completed TODOs."""
        logs = []
        # Filter for memories that look like tasks or have 'todo' tags
        task_memories = [m for m in memories if m.type == MemoryType.PROJECT and ("todo" in m.tags or "task" in m.tags or "fix" in m.title.lower())]
        
        if not task_memories:
            return logs

        # Get current pending todos from service
        try:
            pending_todos = await self.todo_service.list_pending_by_project(project_id) if project_id else []
            pending_titles = {t.title.lower() for t in pending_todos}

            for mem in task_memories:
                if "todo" in mem.tags:
                    is_pending = any(mem.title.lower() in p_title or p_title in mem.title.lower() for p_title in pending_titles)
                    
                    if not is_pending:
                        success = await self.storage.delete(mem.id)
                        if success:
                            logs.append({
                                "id": mem.id,
                                "action": "DELETED",
                                "reason": "FULFILLED",
                                "details": f"Task '{mem.title}' is no longer in pending TODOs.",
                                "timestamp": datetime.utcnow().isoformat()
                            })
                            logger.info(f"[Pruning] Silently deleted fulfilled task memory {mem.id}")
        except Exception as e:
            logger.warning(f"[Pruning] Failed to check fulfilled tasks: {e}")
            
        return logs

    async def _prune_semantically(self, memories: List[MemoryEntry], project_id: Optional[int]) -> List[dict]:
        """Use LLM to identify redundant or stale memories against project context."""
        if not memories:
            return []

        # Gather context
        project_root = await self.project_context.get_project_structure(project_id) if project_id else "No project root found"
        readme = await self.project_context.extract_description_from_readme(project_id) if project_id else ""
        
        # Batch evaluation
        batch = memories[:20]
        
        # Build prompt using standardized builder
        from app.core.memory.prompts import MemoryPruningPromptBuilder
        builder = MemoryPruningPromptBuilder(
            strategy="semantic_pruning",
            project_root=project_root,
            readme=readme,
            memories_text=self._format_memories_for_eval(batch)
        )
        pruning_messages = await builder.build()

        try:
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=pruning_messages,
                purpose="memory_pruning",
                model_name=model_name,
            )
            
            content = response.content
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if not match:
                return []
                
            deletions = json.loads(match.group(0))
            logs = []
            for d in deletions:
                mem_id = d.get("id")
                if mem_id:
                    success = await self.storage.delete(mem_id)
                    if success:
                        logs.append({
                            "id": mem_id,
                            "action": "DELETED",
                            "reason": d.get("reason"),
                            "details": d.get("details"),
                            "timestamp": datetime.utcnow().isoformat()
                        })
            return logs
        except Exception as e:
            logger.error(f"[Pruning] Semantic pruning failed: {e}")
            return []

    def _format_memories_for_eval(self, memories: List[MemoryEntry]) -> str:
        return "\n".join([f"ID: {m.id} | Title: {m.title} | Content: {m.content}" for m in memories])


class MemoryConsolidator:
    """Semantic merger for fragmented memories."""
    def __init__(self, storage):
        self.storage = storage

    async def consolidate(self, memories: List[MemoryEntry], project_id: Optional[int]) -> List[dict]:
        """Find related memories and merge them into high-quality Concepts."""
        if len(memories) < 2:  # Lowered for simulation and small projects
            return []
            
        logs = []
        # Build prompt using standardized builder
        from app.core.memory.prompts import MemoryPruningPromptBuilder
        builder = MemoryPruningPromptBuilder(
            strategy="consolidation",
            memories_text=self._format_memories(memories)
        )
        consolidation_messages = await builder.build()

        try:
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=consolidation_messages,
                purpose="memory_consolidation",
                model_name=model_name,
            )
            content = response.content
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if not match:
                return []
            
            clusters = json.loads(match.group(0))
            for cluster in clusters:
                new_data = cluster.get("merged")
                orig_ids = cluster.get("original_ids", [])
                
                if new_data and orig_ids:
                    from app.core.memory.models import MemoryType, MemoryTier
                    new_entry = MemoryEntry(
                        title=new_data["title"],
                        content=new_data["content"],
                        type=MemoryType.CONCEPT,
                        tier=MemoryTier.STRATEGIC,
                        utility_score=new_data.get("utility_score", 0.9),
                        project_id=project_id,
                        source="consolidation",
                        tags=["consolidated"]
                    )
                    await self.storage.save(new_entry)
                    for oid in orig_ids:
                        await self.storage.delete(oid)
                        logs.append({
                            "id": oid,
                            "action": "DELETED",
                            "reason": "CONSOLIDATED",
                            "details": f"Merged into {new_entry.id}",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    logs.append({
                        "id": new_entry.id,
                        "action": "CREATED",
                        "reason": "CONSOLIDATION_RESULT",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            return logs
        except Exception as e:
            logger.warning(f"[Consolidation] Failed: {e}")
            return []

    def _format_memories(self, memories: List[MemoryEntry]) -> str:
        return "\n".join([f"ID: {m.id} | Title: {m.title} | Content: {m.content[:200]}" for m in memories])
