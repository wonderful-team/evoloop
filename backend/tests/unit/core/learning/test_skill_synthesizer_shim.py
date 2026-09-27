"""Coverage for the backward-compatible synthesizer shim."""

from __future__ import annotations

from app.core.learning.skills import synthesizer as shim
from app.core.learning.workflow_synthesizer import (
    SynthesisMode,
    SynthesisResult,
    SynthesizedMacro,
    SynthesizedSkill,
    WorkflowSynthesizer,
)


def test_shim_re_exports_workflow_synthesizer_api():
    assert shim.WorkflowSynthesizer is WorkflowSynthesizer
    assert shim.SynthesisResult is SynthesisResult
    assert shim.SynthesizedSkill is SynthesizedSkill
    assert shim.SynthesizedMacro is SynthesizedMacro
    assert shim.SynthesisMode is SynthesisMode


def test_shim_all_matches():
    assert set(shim.__all__) == {
        "SynthesisMode",
        "SynthesisResult",
        "SynthesizedMacro",
        "SynthesizedSkill",
        "WorkflowSynthesizer",
    }
