"""Template factory: AppMap x template instantiation -> macro candidates."""

from app.core.atlas.source.macro_factory.synthesizer import (
    SynthesisResult,
    pick_template,
    synthesize,
)
from app.core.atlas.source.macro_factory.templates import MacroCandidate

__all__ = ["MacroCandidate", "SynthesisResult", "pick_template", "synthesize"]
