"""Backward-compatible shim for the workflow synthesizer module.

The canonical implementation now lives in ``app.core.learning.workflow_synthesizer``.
This module re-exports the public API so existing imports continue to work.
"""

from app.core.learning.workflow_synthesizer import (
    SynthesisMode,
    SynthesisResult,
    SynthesizedMacro,
    SynthesizedSkill,
    WorkflowSynthesizer,
)

__all__ = [
    "SynthesisMode",
    "SynthesisResult",
    "SynthesizedMacro",
    "SynthesizedSkill",
    "WorkflowSynthesizer",
]
