"""
Automatic Memory Extraction - Forked Agent Pattern

Inspired by Claude Code's extractMemories.ts, this module implements:
- Automatic memory extraction at conversation end
- Frequency control (throttling)
- Mutual exclusion (skip if main agent already wrote memories)
- Background execution (non-blocking)

Usage:
    from app.core.memory.config import MemoryConfig
    from app.core.memory.manager import MemoryManager
    
    config = MemoryConfig.from_settings()
    manager = MemoryManager()  # or use factory
    extractor = AutoMemoryExtractor(
        memory_manager=manager,
        config=config,
    )
    
    # At end of conversation
    asyncio.create_task(
        extractor.maybe_extract(
            thread_id=thread_id,
            messages=messages,
            project_id=project_id,
        )
    )
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage

from app.core.config import settings
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class AutoMemoryExtractor:
    """
    Automatic memory extraction using forked agent pattern.
    
    This runs at the end of conversations to automatically extract
    valuable information without requiring the user to say "remember".
    
    Usage:
        from app.core.memory.config import MemoryConfig
        from app.core.memory.manager import MemoryManager
        
        config = MemoryConfig.from_settings()
        manager = MemoryManager()  # or use factory
        extractor = AutoMemoryExtractor(
            memory_manager=manager,
            config=config,
        )
    """
    
    def __init__(
        self,
        memory_manager,
        config=None,
        extraction_interval: int = None,
        max_turns: int = 5,
        min_messages: int = None,
    ):
        """
        Initialize auto memory extractor.
        
        Args:
            memory_manager: Memory manager instance (required)
            config: Memory configuration. Uses defaults if None.
            extraction_interval: Extract every N turns (from config if None)
            max_turns: Max turns for extraction agent
            min_messages: Minimum messages to trigger extraction (from config if None)
        """
        self._memory_manager = memory_manager
        self._config = config
        
        # Get values from config if provided, otherwise use settings
        if config is not None:
            self.extraction_interval = extraction_interval or config.extraction_interval
            self.min_messages = min_messages or config.min_messages_for_extraction
        else:
            self.extraction_interval = extraction_interval or getattr(settings, 'AUTO_MEMORY_EXTRACTION_INTERVAL', 1)
            self.min_messages = min_messages or 4
        
        self.max_turns = max_turns
        
        # State tracking
        self._turns_since_extraction: Dict[str, int] = {}
        self._last_message_uuid: Dict[str, str] = {}
        self._extraction_locks: Dict[str, asyncio.Lock] = {}
    
    def _get_lock(self, thread_id: str) -> asyncio.Lock:
        """Get or create lock for thread."""
        if thread_id not in self._extraction_locks:
            self._extraction_locks[thread_id] = asyncio.Lock()
        return self._extraction_locks[thread_id]
    
    async def maybe_extract(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        project_id: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> Optional[List[MemoryEntry]]:
        """
        Conditionally trigger memory extraction.
        
        This is the main entry point. It checks all gates before running
        the actual extraction.
        
        Args:
            thread_id: Conversation thread ID
            messages: List of conversation messages
            project_id: Associated project ID
            user_id: User ID
            
        Returns:
            List of extracted memories, or None if skipped
        """
        # Gate 0: Thread lock to prevent concurrent extractions
        lock = self._get_lock(thread_id)
        if lock.locked():
            logger.debug(f"[AutoExtract] Extraction already in progress for {thread_id}")
            return None
        
        async with lock:
            return await self._extract_with_gates(thread_id, messages, project_id, user_id)
    
    async def _extract_with_gates(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        project_id: Optional[int],
        user_id: Optional[str],
    ) -> Optional[List[MemoryEntry]]:
        """Run extraction with all gating logic."""
        
        # Gate 1: Minimum message count
        if len(messages) < self.min_messages:
            logger.debug(f"[AutoExtract] Skip: only {len(messages)} messages (< {self.min_messages})")
            return None
        
        # Gate 2: Frequency control (throttling)
        turns_count = self._turns_since_extraction.get(thread_id, 0) + 1
        self._turns_since_extraction[thread_id] = turns_count
        
        if turns_count < self.extraction_interval:
            logger.debug(f"[AutoExtract] Skip: throttled ({turns_count}/{self.extraction_interval})")
            return None
        
        self._turns_since_extraction[thread_id] = 0
        
        # Gate 3: Skip if main agent already wrote memories this turn
        if self._has_memory_writes(messages, thread_id):
            logger.info(f"[AutoExtract] Skip: main agent already wrote memories")
            return None
        
        # Gate 4: Check if auto-extraction is enabled
        if not getattr(settings, 'AUTO_MEMORY_EXTRACTION', True):
            logger.debug("[AutoExtract] Skip: auto-extraction disabled")
            return None
        
        # Run extraction
        logger.info(f"[AutoExtract] Starting extraction for thread {thread_id}")
        
        try:
            extracted = await self._run_extraction(
                thread_id=thread_id,
                messages=messages,
                project_id=project_id,
                user_id=user_id,
            )
            
            # Update cursor position
            last_msg = messages[-1]
            if hasattr(last_msg, 'id') and last_msg.id:
                self._last_message_uuid[thread_id] = str(last_msg.id)
            
            return extracted
            
        except Exception as e:
            logger.error(f"[AutoExtract] Extraction failed: {e}", exc_info=True)
            return None
    
    def _has_memory_writes(
        self,
        messages: List[BaseMessage],
        thread_id: str,
    ) -> bool:
        """
        Check if main agent already wrote memories in this turn.
        
        This prevents duplicate extraction when the main agent
        already used the `remember` tool.
        """
        # Get messages since last extraction
        last_uuid = self._last_message_uuid.get(thread_id)
        
        # Find start position
        start_idx = 0
        if last_uuid:
            for i, msg in enumerate(messages):
                if hasattr(msg, 'id') and str(msg.id) == last_uuid:
                    start_idx = i + 1
                    break
        
        # Check recent messages for remember tool calls
        recent_messages = messages[start_idx:]
        
        for msg in reversed(recent_messages):
            if isinstance(msg, AIMessage):
                # Check for remember tool usage
                content = str(msg.content).lower()
                if "remember" in content or "✅ remembered" in content:
                    return True
                
                # Check tool calls if present
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get('name', '') if isinstance(tc, dict) else getattr(tc, 'name', '')
                        if 'remember' in tool_name.lower():
                            return True
                
                # Only check the last assistant message
                break
        
        return False
    
    async def _run_extraction(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        project_id: Optional[int],
        user_id: Optional[str],
    ) -> List[MemoryEntry]:
        """
        Run the actual extraction using a forked agent.
        
        This uses a simplified agent that:
        1. Analyzes the conversation
        2. Extracts 0-3 memories worth keeping
        3. Uses the `remember` tool to save them
        """
        # Build extraction prompt
        prompt = self._build_extraction_prompt(messages)
        
        # Get existing memories to avoid duplicates
        existing_memories = await self._get_existing_memory_manifest()
        
        # Build the full prompt
        full_prompt = f"""{prompt}

## Existing Memories (check to avoid duplicates)
{existing_memories}

## Conversation to Analyze
{self._format_messages(messages[-15:])}  # Last 15 messages

Extract 0-3 memories from this conversation and save them using the remember tool.
Return your response as a JSON array of memories:
```json
[
  {{
    "content": "What to remember",
    "context": "Why this matters (optional)",
    "type": "user|feedback|project|reference"
  }}
]
```

Return empty array `[]` if nothing worth remembering."""

        # Call LLM for extraction using InternalLLMService
        try:
            from app.core.llm import InternalLLMService
            response = await InternalLLMService.invoke(
                messages=[
                    {"role": "system", "content": "You are a memory extraction assistant. Extract valuable information worth remembering from conversations."},
                    {"role": "user", "content": full_prompt}
                ],
                purpose="memory_extraction",
            )
            
            # Parse extracted memories
            content = response.content if hasattr(response, 'content') else str(response)
            extracted = self._parse_extraction_response(content, project_id, user_id)
            
            # Save extracted memories
            saved_count = 0
            for entry in extracted:
                try:
                    await self._memory_manager.save_memory(entry)
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"[AutoExtract] Failed to save memory {entry.id}: {e}")
            
            logger.info(f"[AutoExtract] Saved {saved_count} memories for thread {thread_id}")
            return extracted
            
        except Exception as e:
            logger.error(f"[AutoExtract] LLM extraction failed: {e}")
            return []
    
    def _build_extraction_prompt(self, messages: List[BaseMessage]) -> str:
        """Build the extraction prompt template."""
        return render_template(
            "memory/auto_extraction.prompt.j2",
            message_count=len(messages),
        )
    
    def _format_messages(self, messages: List[BaseMessage]) -> str:
        """Format messages for the extraction prompt."""
        lines = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                role = "User"
            elif isinstance(msg, AIMessage):
                role = "Assistant"
            else:
                role = "System"
            
            content = str(msg.content)[:500]  # Truncate long messages
            if len(str(msg.content)) > 500:
                content += "..."
            
            lines.append(f"{role}: {content}")
        
        return "\n\n".join(lines)
    
    async def _get_existing_memory_manifest(self) -> str:
        """Get a summary of existing memories to avoid duplicates."""
        try:
            memories = await self._memory_manager.list_memories(limit=20)
            
            if not memories:
                return "No existing memories yet."
            
            lines = [f"Total: {len(memories)} recent memories", ""]
            for mem in memories:
                lines.append(f"- [{mem.type.value}] {mem.title}: {mem.description[:80]}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"[AutoExtract] Failed to get memory manifest: {e}")
            return "Could not load existing memories."
    
    def _calculate_confidence(self, content: str, item: dict) -> float:
        """Calculate confidence score based on content quality.
        
        Factors:
        - Content length (50-500 chars is ideal)
        - Specific indicators (file paths, dates, technical terms)
        - Clear structure (bullet points, numbered lists)
        - Actionability (clear instructions vs vague statements)
        """
        import re
        
        score = 0.5  # Base score
        
        # Length factor (ideal: 100-500 chars)
        content_len = len(content)
        if 100 <= content_len <= 500:
            score += 0.2
        elif 50 <= content_len < 100:
            score += 0.1
        elif content_len > 1000:  # Too long, might be noisy
            score -= 0.1
        elif content_len < 30:  # Too short
            score -= 0.2
        
        # Specific indicators
        # File paths
        if re.search(r'[\w\-./]+\.(py|js|ts|java|go|rs|cpp|c|h|md|txt|json|yaml|yml)', content):
            score += 0.1
        
        # Dates or versions
        if re.search(r'\d{4}-\d{2}-\d{2}|v?\d+\.\d+', content):
            score += 0.05
        
        # Technical terms
        tech_terms = ['function', 'class', 'method', 'api', 'database', 'config', 
                     'server', 'client', 'request', 'response', 'error', 'bug']
        if any(term in content.lower() for term in tech_terms):
            score += 0.05
        
        # Clear structure indicators
        if re.search(r'^[\s]*[-*\d]\s+', content, re.MULTILINE):  # List items
            score += 0.05
        
        # Actionability indicators
        action_words = ['should', 'must', 'need to', 'use', 'prefer', 'always', 'never']
        if any(word in content.lower() for word in action_words):
            score += 0.05
        
        # Vague indicators (penalty)
        vague_words = ['maybe', 'perhaps', 'something', 'somehow', 'might', 'could be']
        vague_count = sum(1 for word in vague_words if word in content.lower())
        score -= vague_count * 0.05
        
        # LLM-provided confidence (if available)
        if "confidence" in item:
            try:
                llm_conf = float(item["confidence"])
                # Blend with our calculation
                score = (score + llm_conf) / 2
            except (ValueError, TypeError):
                pass
        
        return max(0.1, min(1.0, score))  # Clamp between 0.1 and 1.0
    
    def _generate_title(self, content: str) -> str:
        """Generate a meaningful title from content.
        
        Uses the first sentence if it's short enough,
        otherwise extracts key terms or truncates.
        """
        import re
        
        # Try first sentence
        first_sentence = re.split(r'[.!?。！？]\s+', content)[0].strip()
        if len(first_sentence) <= 80:
            return first_sentence
        
        # Look for specific patterns
        # Code/file references
        file_ref = re.search(r'`([^`]+\.(py|js|ts|java|go|rs|cpp|h|md|json))`', content)
        if file_ref:
            return f"File: {file_ref.group(1)}"
        
        # Technical terms pattern
        tech_match = re.search(r'(?:using|use|implement|create|build|setup)\s+([\w\s]{10,40})', content, re.IGNORECASE)
        if tech_match:
            return f"How to {tech_match.group(0)}"
        
        # Default: truncate at word boundary
        if len(content) > 80:
            return content[:77].rsplit(' ', 1)[0] + "..."
        return content
    
    def _parse_extraction_response(
        self,
        response: str,
        project_id: Optional[int],
        user_id: Optional[str],
    ) -> List[MemoryEntry]:
        """Parse LLM extraction response into memory entries."""
        import json
        import re
        import uuid
        
        entries = []
        seen_contents = set()  # For deduplication
        
        # Try to extract JSON from response
        try:
            # Find JSON block
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try parsing the whole response
                data = json.loads(response)
            
            if not isinstance(data, list):
                logger.warning(f"[AutoExtract] Expected array, got {type(data)}")
                return []
            
            for item in data:
                if not isinstance(item, dict):
                    continue
                
                content = item.get("content", "").strip()
                if not content:
                    continue
                
                # Deduplication: skip if very similar content already seen
                content_normalized = re.sub(r'\s+', ' ', content.lower())[:100]
                if content_normalized in seen_contents:
                    logger.debug(f"[AutoExtract] Skipping duplicate: {content[:40]}...")
                    continue
                seen_contents.add(content_normalized)
                
                # Determine memory type
                type_str = item.get("type", "project").lower()
                try:
                    mem_type = MemoryType(type_str)
                except ValueError:
                    mem_type = MemoryType.PROJECT
                
                # Determine privacy
                privacy = PrivacyLevel.PRIVATE if mem_type in (MemoryType.USER, MemoryType.FEEDBACK) else PrivacyLevel.TEAM
                
                # Calculate dynamic confidence based on content quality
                confidence = self._calculate_confidence(content, item)
                
                # Skip low-confidence extractions
                if confidence < 0.4:
                    logger.debug(f"[AutoExtract] Skipping low-confidence ({confidence:.2f}): {content[:40]}...")
                    continue
                
                # Generate meaningful title
                title = self._generate_title(content)
                
                entry = MemoryEntry(
                    id=f"auto_{mem_type.value}_{uuid.uuid4().hex[:8]}",
                    type=mem_type,
                    privacy=privacy,
                    title=title,
                    content=content,
                    description=content[:200],
                    project_id=project_id,
                    user_id=user_id,
                    tags=["auto_extracted"],
                    source="auto_extraction",
                    confidence=confidence,
                    extra={
                        "context": item.get("context", ""),
                        "extracted_at": datetime.utcnow().isoformat(),
                    } if item.get("context") else {"extracted_at": datetime.utcnow().isoformat()},
                )
                
                entries.append(entry)
                
        except json.JSONDecodeError as e:
            logger.warning(f"[AutoExtract] Failed to parse JSON: {e}")
        except Exception as e:
            logger.error(f"[AutoExtract] Parse error: {e}")
        
        return entries


async def _get_auto_extractor() -> AutoMemoryExtractor:
    """Get auto-extractor from global MemoryLifespanManager (singleton)."""
    from app.core.memory.lifespan import MemoryLifespanManager
    
    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()
    
    return MemoryLifespanManager.get_container().auto_extractor


async def _shutdown_auto_extractor():
    """Shutdown the global auto-extractor (cleanup)."""
    global _auto_extractor_container, _auto_extractor_instance
    
    if _auto_extractor_container is not None:
        await _auto_extractor_container.shutdown()
        _auto_extractor_container = None
        _auto_extractor_instance = None


class _LazyAutoExtractor:
    """
    Lazy wrapper for auto-extractor singleton.
    
    This allows importing auto_extractor without triggering
    immediate initialization of the memory system.
    """
    
    async def _get_extractor(self) -> AutoMemoryExtractor:
        """Internal async method to get initialized extractor."""
        return await _get_auto_extractor()
    
    async def maybe_extract(self, *args, **kwargs) -> Optional[List[MemoryEntry]]:
        """Delegate maybe_extract to actual extractor."""
        extractor = await self._get_extractor()
        return await extractor.maybe_extract(*args, **kwargs)


# Global lazy auto-extractor instance for convenience imports
# Usage: from app.core.memory.auto_extraction import auto_extractor
auto_extractor = _LazyAutoExtractor()


async def trigger_auto_extraction(
    thread_id: str,
    messages: List[BaseMessage],
    project_id: Optional[int] = None,
    user_id: Optional[str] = None,
) -> Optional[List[MemoryEntry]]:
    """
    Convenience function to trigger auto-extraction.
    
    This is a fire-and-forget style function that can be called
    from anywhere to trigger automatic memory extraction.
    
    Uses a singleton container that persists across calls for efficiency.
    
    Args:
        thread_id: Conversation thread ID
        messages: List of conversation messages
        project_id: Associated project ID
        user_id: User ID
        
    Returns:
        List of extracted memories, or None if skipped/failed
        
    Example:
        from app.core.memory.auto_extraction import trigger_auto_extraction
        
        asyncio.create_task(
            trigger_auto_extraction(
                thread_id=thread_id,
                messages=messages,
                project_id=project_id,
                user_id=user_id,
            )
        )
    """
    extractor = await _get_auto_extractor()
    return await extractor.maybe_extract(
        thread_id=thread_id,
        messages=messages,
        project_id=project_id,
        user_id=user_id,
    )
