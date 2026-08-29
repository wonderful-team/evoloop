"""
Learning Ecosystem - Core Entry Point
Exposes key services and singletons for skill lifecycle management.

Lazy exports: ``import app.core.learning.macro.event`` (or any submodule) must
not pull the heavy skill-synthesis stack into the import chain — low-level
producers (e.g. app.core.events.publishers) import ``learning.macro.event``
while loading config infra, so this package __init__ must stay weightless.
"""

from __future__ import annotations

import importlib

__all__ = [
    # 发现
    "skill_discovery",
    "SkillMatch",
    "SkillDiscovery",
    # 合成器
    "WorkflowSynthesizer",
    "MultimodalSkillSynthesizer",
    "RecordingSession",
    # 解析
    "TraceParser",
    "TraceSequence",
]

_SYMBOL_MODULES: dict[str, str] = {
    "skill_discovery": "app.core.learning.skills.discovery",
    "SkillMatch": "app.core.learning.skills.discovery",
    "SkillDiscovery": "app.core.learning.skills.discovery",
    "WorkflowSynthesizer": "app.core.learning.workflow_synthesizer",
    "MultimodalSkillSynthesizer": "app.core.learning.multimodal_synthesizer",
    "RecordingSession": "app.core.learning.multimodal_synthesizer",
    "TraceParser": "app.core.learning.trace.parser",
    "TraceSequence": "app.core.learning.trace.parser",
}


def __getattr__(name: str):
    module_path = _SYMBOL_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
