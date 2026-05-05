"""
Automatic Memory Extraction - Forked Agent Pattern

Inspired by Claude Code's extractMemories.ts, this module implements:
- Automatic memory extraction at conversation end
- Frequency control (throttling)
- Mutual exclusion (skip if main agent already wrote memories)
- Background execution (non-blocking)
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from app.core.config import settings
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.core.memory.sentiment_markers import (
    ACTION_MARKERS,
    VAGUE_MARKERS,
    _ACTION_PATTERN_EN,
    _VAGUE_PATTERN_EN,
)
from app.utils import render_template

logger = logging.getLogger(__name__)


class AutoMemoryExtractor:
    """
    Automatic memory extraction using forked agent pattern.
    
    This runs at the end of conversations to automatically extract
    valuable information without requiring the user to say "remember".
    
    Usage:
        from app.core.memory.lifespan import MemoryLifespanManager
        
        extractor = MemoryLifespanManager.get_container().auto_extractor
        
        # At end of conversation
        await extractor.maybe_extract(...)
    """

    def __init__(
        self,
        memory_manager,
        config=None,
        extraction_interval: int = None,
        max_turns: int = 5,
        min_messages: int = None,
        term_bank=None,
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
        self._term_bank = term_bank

        # Get values from config if provided, otherwise use settings
        if config is not None:
            self.extraction_interval = extraction_interval or config.extraction_interval
            self.min_messages = min_messages or config.min_messages_for_extraction
        else:
            self.extraction_interval = extraction_interval or getattr(settings, 'AUTO_MEMORY_EXTRACTION_INTERVAL', 1)
            self.min_messages = min_messages or 4

        self.max_turns = max_turns

        # State tracking
        self._turns_since_extraction: dict[str, int] = {}
        self._last_message_uuid: dict[str, str] = {}
        self._extraction_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, thread_id: str) -> asyncio.Lock:
        """Get or create lock for thread."""
        if thread_id not in self._extraction_locks:
            self._extraction_locks[thread_id] = asyncio.Lock()
        return self._extraction_locks[thread_id]

    async def maybe_extract(
        self,
        thread_id: str,
        messages: list[BaseMessage],
        project_id: int | None = None,
        user_id: str | None = None,
        summary: str | None = None,
        run_id: str | None = None,
        force: bool = False
    ) -> list[MemoryEntry] | None:
        """
        Conditionally trigger memory extraction.
        
        This is the main entry point. It checks all gates before running
        the actual extraction.
        
        Args:
            thread_id: Conversation thread ID
            messages: List of conversation messages
            project_id: Associated project ID
            user_id: User ID
            summary: Optional conversation summary
            force: Whether to bypass gating logic
            
        Returns:
            List of extracted memories, or None if skipped
        """
        # Gate 0: Thread lock to prevent concurrent extractions
        lock = self._get_lock(thread_id)
        if lock.locked():
            logger.debug(f"[AutoExtract] Extraction already in progress for {thread_id}")
            return None

        async with lock:
            return await self._extract_with_gates(
                thread_id, messages, project_id, user_id, summary, run_id, force
            )

    async def _extract_with_gates(
        self,
        thread_id: str,
        messages: list[BaseMessage],
        project_id: int | None,
        user_id: str | None,
        summary: str | None,
        run_id: str | None = None,
        force: bool = False
    ) -> list[MemoryEntry] | None:
        """Run extraction with all gating logic."""

        # Gate 1: Minimum message count
        if not force and len(messages) < self.min_messages:
            logger.debug(f"[AutoExtract] Skip: only {len(messages)} messages (< {self.min_messages})")
            return None

        # Gate 2: Frequency control (throttling)
        turns_count = self._turns_since_extraction.get(thread_id, 0) + 1
        self._turns_since_extraction[thread_id] = turns_count

        if not force and turns_count < self.extraction_interval:
            logger.debug(f"[AutoExtract] Skip: throttled ({turns_count}/{self.extraction_interval})")
            return None

        self._turns_since_extraction[thread_id] = 0

        # Gather project context for term extraction
        project_context = ""
        if project_id:
            try:
                project_context = await self._gather_multi_source_context(project_id)
            except Exception as e:
                logger.debug(f"[AutoExtract] Failed to gather project context: {e}")

        # Discover terms from raw messages regardless of extraction gates
        if self._term_bank and project_id:
            try:
                combined_text = "\n".join([str(m.content) for m in messages])
                await self._term_bank.discover(
                    combined_text,
                    project_id=project_id,
                    project_context=project_context,
                )
            except Exception as e:
                logger.debug(f"[AutoExtract] Raw message discovery failed: {e}")

        # Gate 3: Skip if main agent already wrote memories this turn
        if not force and self._has_memory_writes(messages, thread_id):
            logger.info("[AutoExtract] Skip: main agent already wrote memories")
            return None

        # Gate 4: Check if auto-extraction is enabled
        if not getattr(settings, 'AUTO_MEMORY_EXTRACTION', True):
            logger.debug("[AutoExtract] Skip: auto-extraction disabled")
            return None

        logger.info(f"[AutoExtract] Starting extraction for thread {thread_id}")

        try:
            # Standardize source_message_id using msg-{thread_id}-{sequence_number}
            # This is critical for atomic cleanup during session rewinds.
            last_msg = messages[-1]
            last_msg_id = None
            seq = None
            
            # 1. Try to get sequence_number from metadata
            # Handle both LangChain (additional_kwargs) and DB Model (meta_data / sequence_number)
            if hasattr(last_msg, "additional_kwargs") and last_msg.additional_kwargs:
                seq = last_msg.additional_kwargs.get("sequence_number")
            elif hasattr(last_msg, "meta_data") and last_msg.meta_data:
                seq = (last_msg.meta_data or {}).get("sequence_number")
            
            if seq is None and hasattr(last_msg, "sequence_number"):
                seq = last_msg.sequence_number
            
            # 2. Fallback: If sequence is missing but we have a standardized ID string, parse it
            # This handles cases where LangChain ID was updated but metadata was lost.
            if seq is None and last_msg.id:
                msg_id_str = str(last_msg.id)
                if msg_id_str.startswith("msg-"):
                    parts = msg_id_str.split("-")
                    if len(parts) >= 3:
                        try:
                            seq = int(parts[-1])
                        except (ValueError, TypeError):
                            pass

            # 3. Final Fallback: If still missing but we have a UUID, query DB
            # This handles cases where LangGraph state lost all in-memory updates.
            if seq is None and last_msg.id:
                msg_uuid = str(last_msg.id)
                try:
                    from app.infrastructure.database.sql.database import session_scope
                    from app.models import Message
                    from sqlalchemy import select
                    async with session_scope() as session:
                        stmt = select(Message.sequence_number).where(Message.thread_id == thread_id)
                        if msg_uuid.isdigit():
                            stmt = stmt.where(Message.id == int(msg_uuid))
                        
                        result = await session.execute(stmt.order_by(Message.sequence_number.desc()).limit(1))
                        db_seq = result.scalar_one_or_none()
                        if db_seq is not None:
                            seq = db_seq
                            logger.debug(f"[AutoExtract] Resolved sequence {seq} from DB for message {msg_uuid}")
                except Exception as db_err:
                    logger.debug(f"[AutoExtract] DB sequence lookup failed: {db_err}")

            if seq is not None:
                last_msg_id = f"msg-{thread_id}-{seq}"
            elif last_msg.id:
                # Last resort fallback to raw ID
                last_msg_id = str(last_msg.id)
            
            if last_msg_id:
                self._last_message_uuid[thread_id] = last_msg_id

            extracted = await self._run_extraction(
                thread_id=thread_id,
                messages=messages,
                project_id=project_id,
                user_id=user_id,
                summary=summary,
                source_message_id=last_msg_id,
                run_id=run_id,
                project_context=project_context,
            )

            return extracted

        except Exception as e:
            logger.error(f"[AutoExtract] Extraction failed: {e}", exc_info=True)
            return None

    def _has_memory_writes(
        self,
        messages: list[BaseMessage],
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
                if str(msg.id) == last_uuid:
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
                if msg.tool_calls:
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
        messages: list[BaseMessage],
        project_id: int | None = None,
        user_id: str | None = None,
        summary: str | None = None,
        source_message_id: str | None = None,
        run_id: str | None = None,
        project_context: str = "",
    ) -> list[MemoryEntry]:
        """
        Run extraction logic using a forked agent pattern.
        """
        # Use provided context or gather fresh
        multi_source_context = project_context
        if not multi_source_context:
            multi_source_context = await self._gather_multi_source_context(project_id)
        logger.info(f"[AutoExtract] Multi-source context length: {len(multi_source_context)}")
        # Build extraction prompt using standardized builder
        from app.core.memory.prompts import MemoryExtractionPromptBuilder

        # Extract metadata from multi-source context
        readme_summary = multi_source_context.split("### README.md")[-1].split("###")[0].strip() if "### README.md" in multi_source_context else "None"
        pending_todos = multi_source_context.split("### Pending TODOs")[-1].split("###")[0].strip() if "### Pending TODOs" in multi_source_context else "None"
        existing_memories = await self._get_existing_memory_manifest()

        # Inject discovered domain terms so LLM knows project vocabulary
        domain_terms = []
        if self._term_bank is not None:
            try:
                domain_terms = await self._term_bank.get_top_terms(
                    project_id, limit=20
                )
            except Exception as e:
                logger.debug(f"[AutoExtract] Failed to load domain terms: {e}")

        builder = MemoryExtractionPromptBuilder(
            readme_summary=readme_summary,
            pending_todos=pending_todos,
            existing_memories=existing_memories,
            multi_source_context=multi_source_context,
            messages_text=self._format_messages(messages[-15:]),
            summary=summary,
            domain_terms=domain_terms,
        )

        extraction_messages = await builder.build()

        # Call LLM for extraction using InternalLLMService
        try:
            from app.core.llm import InternalLLMService
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=extraction_messages,
                purpose="memory_extraction",
                model_name=model_name,
                max_tokens=4000,
            )

            # Parse extracted memories
            content = response.content
            logger.debug(f"[AutoExtract] Raw LLM response: {content[:500]}...")
            extracted = await self._parse_extraction_response(
                content,
                project_id,
                user_id,
                source_message_id=source_message_id,
                run_id=run_id,
                project_context=project_context,
            )

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

    def _build_extraction_prompt(self, messages: list[BaseMessage]) -> str:
        """Build the extraction prompt template."""
        return render_template(
            "core/memory/auto_extraction.prompt.j2",
            message_count=len(messages),
        )

    def _format_messages(self, messages: list[BaseMessage]) -> str:
        """Format messages for the extraction prompt with smart truncation."""
        lines = []
        for msg in messages:
            role = "System"
            if isinstance(msg, HumanMessage):
                role = "User"
            elif isinstance(msg, AIMessage):
                role = "Assistant"
            elif isinstance(msg, ToolMessage):
                role = f"Tool ({getattr(msg, 'name', 'output')})"

            content_raw = ""
            if isinstance(msg.content, str):
                content_raw = msg.content
            elif isinstance(msg.content, list):
                text_parts = []
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content_raw = " ".join(text_parts)
            else:
                content_raw = str(msg.content)
            
            # Smart Truncation: Head (400) + Tail (300) for very long messages
            if len(content_raw) > 800:
                content = content_raw[:400] + "\n... [TRUNCATED] ...\n" + content_raw[-300:]
            else:
                content = content_raw

            msg_line = f"{role}: {content}"
            logger.info(f"[AutoExtract] Message {len(lines)}: {msg_line[:100]}...")
            lines.append(msg_line)

        formatted = "\n\n".join(lines)
        logger.info(f"[AutoExtract] Formatted {len(lines)} messages for LLM (len: {len(formatted)})")
        return formatted

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

    # ── Domain-agnostic scoring regexes (pre-compiled) ──────────────────
    _RESOURCE_PATH_RE = re.compile(
        r'\b(?:[\w\-]+/)+[\w\-]+(?:\.[\w\-]+)+\b'
    )
    _DATE_RE = re.compile(
        r'\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b'
    )
    _VERSION_RE = re.compile(
        r'\bv\d+\.\d+(?:\.\d+)?(?:[-+.]?[a-zA-Z0-9]+)*\b'
    )
    _LIST_RE = re.compile(
        r'^\s*(?:[-*]|\d+\.)\s+\S', re.MULTILINE
    )
    _NUMBER_RE = re.compile(r'\b\d+(?:\.\d+)?\b')

    # (sentiment markers are module-level imports: _ACTION_PATTERN_EN, _VAGUE_PATTERN_EN)

    async def _calculate_confidence(
        self,
        content: str,
        llm_confidence: float | None = None,
        project_id: int | None = None,
    ) -> float:
        """Calculate confidence score based on content quality.

        Uses tiered mutually-exclusive scoring:
        - Tier A (+0.25): high domain-term density or resource paths
        - Tier B (+0.15): medium domain-term density or specific indicators
        - Tier C (+0.05): structural / actionable quality

        LLM confidence acts as a trust ceiling, not a blended average.
        """
        score = 0.5  # Base score

        # ── Length scoring (continuous trapezoid) ───────────────────────
        content_len = len(content)
        if 100 <= content_len <= 500:
            score += 0.2
        elif 50 <= content_len < 100:
            # Linear ramp from 50 to 100
            score += 0.1 + 0.1 * (content_len - 50) / 50
        elif 500 < content_len <= 1000:
            # Linear decay from 500 to 1000
            score += 0.2 * (1000 - content_len) / 500
        elif content_len > 1000:
            score -= 0.1
        elif content_len < 30:
            score -= 0.15
        else:  # 30-50
            score += 0.05

        # ── Vague-word penalty (capped) ────────────────────────────────
        content_lower = content.lower()
        # Vagueness: English via word-boundary regex, Chinese via substring
        vague_count = len(_VAGUE_PATTERN_EN.findall(content))
        if vague_count < 3:
            vague_count += sum(
                1 for word in VAGUE_MARKERS["zh"] if word in content
            )
            vague_count = min(vague_count, 3)  # Re-apply cap after both langs
        score -= min(vague_count, 3) * 0.05

        # ── Domain-term density (async lookup) ─────────────────────────
        term_density = 0
        if self._term_bank is not None:
            matched = await self._term_bank.match(content, project_id)
            term_density = len(matched)

        # ── Specific indicators ────────────────────────────────────────
        has_resource_path = bool(self._RESOURCE_PATH_RE.search(content))
        has_date = bool(self._DATE_RE.search(content))
        has_version = bool(self._VERSION_RE.search(content))
        has_number = bool(self._NUMBER_RE.search(content))
        has_list = bool(self._LIST_RE.search(content))
        # Actionability: English via word-boundary regex, Chinese via substring
        has_actionable = bool(_ACTION_PATTERN_EN.search(content))
        if not has_actionable:
            has_actionable = any(w in content for w in ACTION_MARKERS["zh"])

        # ── Tiered scoring (mutually exclusive) ────────────────────────
        if term_density >= 3 or has_resource_path:
            score += 0.25  # Tier A
        elif term_density >= 1 or has_date or has_version or has_number:
            score += 0.15  # Tier B
        elif has_list or has_actionable:
            score += 0.05  # Tier C

        # ── LLM confidence: trust ceiling ──────────────────────────────
        if llm_confidence is not None:
            if llm_confidence < 0.3:
                # LLM doesn't trust it → cap regardless of local signals
                score = min(score, 0.6)
            elif llm_confidence > 0.8:
                # LLM is very confident → allow slight boost
                score = min(score * 1.1, 1.0)

        return max(0.1, min(1.0, score))

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

    async def _parse_extraction_response(
        self,
        response: str,
        project_id: int | None,
        user_id: str | None,
        source_message_id: str | None = None,
        run_id: str | None = None,
        project_context: str = "",
    ) -> list[MemoryEntry]:
        """Parse LLM extraction response into memory entries."""
        entries = []
        seen_contents = set()  # For deduplication

        # Try to extract JSON from response
        try:
            response = response.strip()
            if not response:
                logger.info("[AutoExtract] Empty response from LLM, assuming no extractions.")
                return []

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

                # Global Deduplication: Content Fingerprinting (SHA-256)
                content_hash = MemoryEntry.compute_content_hash(content)
                
                # Check if already seen in current session
                if content_hash in seen_contents:
                    logger.debug(f"[AutoExtract] Skipping duplicate in session: {content[:40]}...")
                    continue
                seen_contents.add(content_hash)

                # Check if already exists globally (Cross-session pollution control)
                try:
                    existing = await self._memory_manager.find_by_hash(content_hash, project_id)
                    if existing:
                        logger.info(f"[AutoExtract] Skipping global duplicate: {content[:40]}... (Existing: {existing.id})")
                        continue
                except Exception as e:
                    logger.warning(f"[AutoExtract] Failed global hash check: {e}")

                # Determine memory type
                type_str = item.get("type", "project").lower()
                try:
                    mem_type = MemoryType(type_str)
                except ValueError:
                    mem_type = MemoryType.PROJECT

                # Determine privacy
                privacy = PrivacyLevel.PRIVATE if mem_type in (MemoryType.USER, MemoryType.FEEDBACK) else PrivacyLevel.TEAM

                # Calculate dynamic confidence based on content quality
                llm_conf = item.get("confidence")
                try:
                    llm_confidence = float(llm_conf) if llm_conf is not None else None
                except (ValueError, TypeError):
                    llm_confidence = None

                confidence = await self._calculate_confidence(
                    content,
                    llm_confidence=llm_confidence,
                    project_id=project_id,
                )

                # Skip low-confidence extractions
                if confidence < 0.35:  # Lowered threshold from 0.4
                    logger.info(f"[AutoExtract] ❌ Rejecting low-confidence ({confidence:.2f}): {content[:60]}...")
                    continue

                # Generate meaningful title or use provided one
                title = item.get("title") or self._generate_title(content)

                # Categorization (Tiering)
                tier_str = item.get("tier", "operational").lower()
                from app.core.memory.models import MemoryTier
                try:
                    tier = MemoryTier(tier_str)
                except ValueError:
                    tier = MemoryTier.OPERATIONAL
                    
                utility_score = float(item.get("utility_score", 0.0))
                rationale = item.get("rationale", "")

                logger.info(f"[AutoExtract] Creating memory '{title}' with source_msg={source_message_id}, run_id={run_id}")
                entry = MemoryEntry(
                    id=f"auto_{mem_type.value}_{uuid.uuid4().hex[:8]}",
                    type=mem_type,
                    tier=tier,
                    utility_score=utility_score,
                    privacy=privacy,
                    title=title,
                    content=content,
                    content_hash=content_hash,
                    description=content[:200],
                    project_id=project_id,
                    user_id=user_id,
                    source_message_id=source_message_id,
                    run_id=run_id,
                    tags=["auto_extracted"],
                    source="auto_extraction",
                    confidence=confidence,
                    extra={
                        "context": item.get("context", ""),
                        "time_context": item.get("time_context", ""),
                        "mapping_path": item.get("mapping_path", ""),
                        "rationale": rationale,
                        "extracted_at": datetime.utcnow().isoformat(),
                    },
                )

                entries.append(entry)

                # Discover domain terms from accepted high-confidence memories
                if self._term_bank is not None:
                    try:
                        await self._term_bank.discover(
                            content,
                            project_id=project_id,
                            project_context=project_context,
                        )
                    except Exception as e:
                        logger.debug(f"[AutoExtract] Term discovery failed: {e}")

        except json.JSONDecodeError as e:
            logger.warning(f"[AutoExtract] Failed to parse JSON: {e}")
        except Exception as e:
            logger.error(f"[AutoExtract] Parse error: {e}")

        return entries

    async def _gather_multi_source_context(self, project_id: int | None) -> str:
        """Gather facts from README, Tree structure, and TODOs via event-driven providers."""
        if not project_id:
            return "No project selected."

        from app.core.memory.event.publishers import publish_memory_context_gather

        try:
            event = await publish_memory_context_gather(project_id=project_id)
        except Exception as e:
            logger.warning(f"[AutoExtract] Context gather event failed: {e}")
            return "No multi-source facts available."

        return event.data.to_context_string()


async def trigger_auto_extraction(
    thread_id: str,
    messages: list[BaseMessage],
    project_id: int | None = None,
    user_id: str | None = None,
    run_id: str | None = None,
    force: bool = False,
) -> list[MemoryEntry] | None:
    """
    Convenience function to trigger auto-extraction.
    """
    from app.core.memory.lifespan import MemoryLifespanManager
    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()
    
    extractor = MemoryLifespanManager.get_container().auto_extractor
    return await extractor.maybe_extract(
        thread_id=thread_id,
        messages=messages,
        project_id=project_id,
        user_id=user_id,
        run_id=run_id,
        force=force
    )
