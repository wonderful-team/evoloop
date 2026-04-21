"""
BlackboardParser - Extracts structured blackboard updates from LLM text output.

Decoupled from AgentEngine to keep parsing logic isolated and testable.
"""

import logging
import re
from typing import Any

from app.core.engine.state.blackboard import BlackboardMetadata, BlackboardState

logger = logging.getLogger(__name__)


class BlackboardParser:
    """Parses inferred blackboard updates from LLM response content."""

    @staticmethod
    def parse(content: Any, blackboard: BlackboardState | None, name: str = "Agent") -> BlackboardState:
        """
        Parses the LLM response content for inferred blackboard updates.
        Returns a NEW BlackboardState copy; does NOT mutate the input.
        """
        if not content or not isinstance(content, str):
            return blackboard.model_copy(deep=True) if blackboard else BlackboardState()

        # Support [BLACKBOARD: key=value] pattern
        pattern = r"\[BLACKBOARD:\s*(\w+)\s*=\s*(.*?)\]"
        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            result = blackboard.model_copy(deep=True) if blackboard else BlackboardState()
            metadata = dict(result.metadata) if result.metadata else {}

            for key, val in matches:
                val_str = val.strip()
                if val_str.lower() == "true":
                    val = True
                elif val_str.lower() == "false":
                    val = False
                elif val_str.isdigit():
                    val = int(val_str)
                else:
                    val = val_str

                metadata[key] = val
                logger.info(f"[{name}] Blackboard field '{key}' updated via Inference: {val}")

            result.metadata = BlackboardMetadata.model_validate(metadata)
            return result

        return blackboard.model_copy(deep=True) if blackboard else BlackboardState()
