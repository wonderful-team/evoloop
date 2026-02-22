"""
Memory Consolidation Service (Sleep Cycle).
Responsible for condensing short-term memory (logs/working) into long-term knowledge.
"""
import logging

from app.core.brain.drivers.abstract import BaseBrainDriver
from app.core.brain.filesystem.manager import BrainFileSystem
from app.core.brain.filesystem.protocol import MemoryFile, MemoryZone

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    def __init__(self, reflective_driver: BaseBrainDriver, fs: BrainFileSystem):
        self.llm = reflective_driver
        self.fs = fs

    async def run_cycle(self, source_message_id: str = None):
        """
        Runs the consolidation cycle.
        1. Read recent logs/tasks.
        2. Summarize.
        3. Update knowledge base.
        """
        logger.info("Starting Memory Consolidation Cycle...")

        # 1. Read Current Task State
        # Ensure we use the string value of the Enum
        task_path = f"{MemoryZone.WORKING.value}/{MemoryFile.TASK.value}"
        logger.info(f"Consolidator reading task from: {task_path}")
        task_content = self.fs.read_file(task_path)

        if not task_content or "[Error" in task_content:
            logger.info(f"No active task to consolidate. Read result: {task_content[:50]}")
            return

        # 2. Generate Summary
        logger.info("Generating summary via Reflective Brain...")
        system_prompt = "You are the Reflective Brain. Your job is to summarize the following 'Working Memory' scratchpad into a concise knowledge entry."
        summary = await self.llm.generate(
            context=task_content,
            user_input="Summarize key facts and decisions.",
            system_prompt=system_prompt
        )

        # 3. Append to a daily log in Knowledge Base with ID Anchor
        # For simplicity, just append to a 'journal.md'
        try:
            journal_path = f"{MemoryZone.KNOWLEDGE.value}/journal.md"

            # Format with Anchor if ID provided
            header = "## Consolidated Entry"
            if source_message_id:
                header += f" <!-- id: {source_message_id} -->"

            self.fs.append_file(journal_path, f"\n{header}\n{summary}")

            # 4. Clear the Scratchpad (Idempotency)
            # This ensures we don't consolidate the same task twice if retried.
            logger.info(f"Clearing scratchpad: {task_path}")
            self.fs.write_file(task_path, "")

            logger.info("Consolidation complete.")
        except Exception as e:
            logger.error(f"Consolidation failed: {e}")

    async def remove_entry_by_id(self, source_id: str) -> bool:
        """
        Remove a consolidated entry by its source message ID anchor.
        """
        import re
        try:
            journal_path = f"{MemoryZone.KNOWLEDGE.value}/journal.md"
            content = self.fs.read_file(journal_path)
            if not content:
                return False

            # Regex to find the block:
            # Matches "## Consolidated Entry <!-- id: UUID -->" until the next "## " or EOF
            # Handles optional leading newline and start of string.
            pattern = rf"(?:\n|^)## Consolidated Entry <!-- id: {re.escape(source_id)} -->.*?(?=\n## |\Z)"

            new_content, count = re.subn(pattern, "", content, flags=re.DOTALL)

            if count > 0:
                self.fs.write_file(journal_path, new_content.strip())
                logger.info(f"Removed journal entry for {source_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove entry {source_id}: {e}")
            return False
