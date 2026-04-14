"""
Memory Extraction Service

Automatically extracts durable memories from conversation transcripts.
Inspired by Claude Code's extractMemories.ts
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from app.core.memory.backends.file_backend import FileMemoryStorage
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class MemoryExtractionService:
    """
    Service for automatically extracting memories from conversations.
    
    This service runs as a background task (similar to Claude Code's forked agent)
    to analyze conversation history and extract valuable information worth remembering.
    """
    
    def __init__(
        self,
        storage: Optional[FileMemoryStorage] = None,
        config: Optional['MemoryConfig'] = None,
    ):
        """
        Initialize extraction service.
        
        Args:
            storage: Memory storage backend. Creates default if not provided.
            config: Memory configuration. Uses default if not provided.
        """
        self.storage = storage or FileMemoryStorage()
        self.config = config
    
    async def extract_from_conversation(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        project_id: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """
        Extract memories from a conversation.
        
        Args:
            thread_id: Conversation thread ID
            messages: List of conversation messages
            project_id: Associated project ID
            user_id: User ID
            
        Returns:
            List of extracted memory entries
        """
        if not messages:
            return []
        
        # Get existing memories to avoid duplicates
        existing_memories = await self.storage.list_all()
        existing_manifest = self._format_existing_memories(existing_memories)
        
        # Build extraction prompt
        prompt = self._build_extraction_prompt(
            messages=messages,
            existing_memories=existing_manifest,
        )
        
        # Call LLM for extraction (using background agent pattern)
        try:
            extraction_result = await self._run_extraction_agent(prompt, messages)
            
            # Parse extracted memories
            new_entries = self._parse_extraction_result(
                extraction_result,
                project_id=project_id,
                user_id=user_id,
            )
            
            # Deduplicate against existing memories
            deduplicated = self._deduplicate(new_entries, existing_memories)
            
            # Save new memories
            for entry in deduplicated:
                await self.storage.save(entry)
                logger.info(f"Extracted and saved memory: {entry.id} ({entry.type.value})")
            
            return deduplicated
            
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return []
    
    def _format_existing_memories(self, memories: List[Any]) -> str:
        """
        Format existing memories for prompt context.
        
        Args:
            memories: List of existing memory entries
            
        Returns:
            Formatted manifest string
        """
        if not memories:
            return "No existing memories yet."
        
        lines = [f"Total: {len(memories)} existing memories", ""]
        
        # Group by type
        by_type: Dict[str, List] = {}
        for mem in memories:
            mem_type = mem.type.value if hasattr(mem, 'type') else 'unknown'
            by_type.setdefault(mem_type, []).append(mem)
        
        for mem_type, mems in by_type.items():
            lines.append(f"### {mem_type.upper()}")
            for mem in mems[:10]:  # Limit to 10 per type
                desc = mem.description if hasattr(mem, 'description') else mem.title
                lines.append(f"- {mem.title}: {desc[:80]}")
            if len(mems) > 10:
                lines.append(f"- ... and {len(mems) - 10} more")
            lines.append("")
        
        return "\n".join(lines)
    
    def _build_extraction_prompt(
        self,
        messages: List[BaseMessage],
        existing_memories: str,
    ) -> str:
        """
        Build extraction prompt using template.
        
        Args:
            messages: Conversation messages
            existing_memories: Formatted existing memories
            
        Returns:
            Rendered prompt string
        """
        # Format recent messages for context
        recent_messages = self._format_messages(messages[-20:])  # Last 20 messages
        
        return render_template(
            "memory/extraction.prompt.j2",
            message_count=len(messages),
            recent_messages=recent_messages,
            existing_memories=existing_memories,
        )
    
    def _format_messages(self, messages: List[BaseMessage]) -> str:
        """Format messages for prompt."""
        lines = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                role = "User"
            elif isinstance(msg, AIMessage):
                role = "Assistant"
            else:
                role = "System"
            
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            
            lines.append(f"{role}: {content}")
        
        return "\n\n".join(lines)
    
    async def _run_extraction_agent(
        self,
        prompt: str,
        context_messages: List[BaseMessage],
    ) -> str:
        """
        Run extraction agent to analyze conversation.
        
        Args:
            prompt: Extraction prompt
            context_messages: Conversation context
            
        Returns:
            Extraction result (JSON or structured text)
        """
        # Build messages for LLM
        messages = [
            {"role": "system", "content": prompt},
        ]
        
        # Add context summary
        context_summary = self._format_messages(context_messages[-10:])
        messages.append({
            "role": "user",
            "content": f"Analyze this conversation and extract memories:\n\n{context_summary}",
        })
        
        # Call LLM using InternalLLMService
        from app.core.llm import InternalLLMService
        response = await InternalLLMService.invoke(
            messages=messages,
            purpose="memory_extraction",
        )
        
        return response.content if hasattr(response, 'content') else str(response)
    
    def _parse_extraction_result(
        self,
        result: str,
        project_id: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """
        Parse extraction result into memory entries.
        
        Args:
            result: LLM extraction result
            project_id: Associated project ID
            user_id: User ID
            
        Returns:
            List of parsed memory entries
        """
        import json

        entries = []
        
        # Try JSON parsing first
        try:
            data = json.loads(result)
            if isinstance(data, list):
                for item in data:
                    entry = self._create_entry_from_dict(
                        item,
                        project_id=project_id,
                        user_id=user_id,
                    )
                    if entry:
                        entries.append(entry)
            elif isinstance(data, dict) and "memories" in data:
                for item in data["memories"]:
                    entry = self._create_entry_from_dict(
                        item,
                        project_id=project_id,
                        user_id=user_id,
                    )
                    if entry:
                        entries.append(entry)
        except json.JSONDecodeError:
            # Fallback: parse text format
            entries = self._parse_text_format(result, project_id, user_id)
        
        return entries
    
    def _create_entry_from_dict(
        self,
        data: Dict[str, Any],
        project_id: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> Optional[MemoryEntry]:
        """Create memory entry from dictionary."""
        import uuid
        
        mem_type_str = data.get("type", "project").lower()
        try:
            mem_type = MemoryType(mem_type_str)
        except ValueError:
            logger.warning(f"Unknown memory type: {mem_type_str}")
            return None
        
        # Determine privacy based on type
        privacy_defaults = {
            MemoryType.USER: PrivacyLevel.PRIVATE,
            MemoryType.FEEDBACK: PrivacyLevel.PRIVATE,
            MemoryType.PROJECT: PrivacyLevel.TEAM,
            MemoryType.REFERENCE: PrivacyLevel.TEAM,
        }
        privacy = PrivacyLevel(data.get("privacy", privacy_defaults[mem_type].value))
        
        return MemoryEntry(
            id=f"mem_{mem_type.value}_{uuid.uuid4().hex[:8]}",
            type=mem_type,
            privacy=privacy,
            title=data.get("title", "Untitled"),
            content=data.get("content", data.get("description", "")),
            description=data.get("description", data.get("title", ""))[:200],
            project_id=project_id,
            user_id=user_id,
            tags=data.get("tags", []),
            source="extracted",
            confidence=data.get("confidence", 0.8),
        )
    
    def _parse_text_format(
        self,
        text: str,
        project_id: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """Parse text format extraction result."""
        import re
        import uuid
        
        entries = []
        
        # Look for patterns like:
        # TYPE: user
        # TITLE: User is a Python expert
        # CONTENT: ...
        
        pattern = r"TYPE:\s*(\w+)\s*\nTITLE:\s*(.+?)\s*\nCONTENT:\s*([\s\S]+?)(?=\n\nTYPE:|\Z)"
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        for mem_type_str, title, content in matches:
            try:
                mem_type = MemoryType(mem_type_str.lower())
            except ValueError:
                continue
            
            privacy_defaults = {
                MemoryType.USER: PrivacyLevel.PRIVATE,
                MemoryType.FEEDBACK: PrivacyLevel.PRIVATE,
                MemoryType.PROJECT: PrivacyLevel.TEAM,
                MemoryType.REFERENCE: PrivacyLevel.TEAM,
            }
            
            entries.append(MemoryEntry(
                id=f"mem_{mem_type.value}_{uuid.uuid4().hex[:8]}",
                type=mem_type,
                privacy=privacy_defaults[mem_type],
                title=title.strip(),
                content=content.strip(),
                description=title.strip()[:200],
                project_id=project_id,
                user_id=user_id,
                source="extracted",
                confidence=0.7,
            ))
        
        return entries
    
    def _deduplicate(
        self,
        new_entries: List[MemoryEntry],
        existing_memories: List[Any],
    ) -> List[MemoryEntry]:
        """
        Remove duplicates from new entries.
        
        Args:
            new_entries: Newly extracted entries
            existing_memories: Existing memory entries
            
        Returns:
            Deduplicated list
        """
        # Simple deduplication based on title similarity
        existing_titles = {m.title.lower() for m in existing_memories}
        
        deduplicated = []
        for entry in new_entries:
            # Check title similarity
            if entry.title.lower() in existing_titles:
                logger.debug(f"Skipping duplicate: {entry.title}")
                continue
            
            # Check content similarity (simple substring match)
            is_duplicate = False
            for existing in existing_memories:
                if hasattr(existing, 'content'):
                    # If content is very similar, skip
                    if self._content_similarity(entry.content, existing.content) > 0.8:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                deduplicated.append(entry)
        
        return deduplicated
    
    def _content_similarity(self, content1: str, content2: str) -> float:
        """Calculate simple content similarity (Jaccard index)."""
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)


class MemoryConsolidationService:
    """
    Service for consolidating working memory into long-term storage.
    
    Similar to Brain's MemoryConsolidator but using the new file-based system.
    """
    
    def __init__(self, storage: Optional[FileMemoryStorage] = None):
        self.storage = storage or FileMemoryStorage()
    
    async def consolidate(
        self,
        working_content: str,
        source: str = "consolidated",
    ) -> Optional[MemoryEntry]:
        """
        Consolidate working memory content into long-term storage.
        
        Args:
            working_content: Content from working memory (e.g., task.md)
            source: Source tag for the consolidated memory
            
        Returns:
            Created memory entry or None
        """
        if not working_content or len(working_content.strip()) < 50:
            # Too short to consolidate
            return None
        
        # Generate summary using template
        try:
            summary = render_template(
                "memory/consolidation.prompt.j2",
                content=working_content,
            )
            
            # Create memory entry
            entry = MemoryEntry(
                id=f"mem_consolidated_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title=f"Session Summary {datetime.utcnow().strftime('%Y-%m-%d')}",
                content=summary,
                description=summary[:200],
                source=source,
            )
            
            await self.storage.save(entry)
            logger.info(f"Consolidated working memory to {entry.id}")
            
            return entry
            
        except Exception as e:
            logger.error(f"Consolidation failed: {e}")
            return None
