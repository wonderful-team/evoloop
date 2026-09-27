"""Verification of SynthesizedMacro.to_yaml dead-code removal."""

from __future__ import annotations

from app.core.learning.workflow_synthesizer import SynthesizedMacro, SynthesizedSkill


class TestSynthesizedArtifact:
    def test_macro_to_yaml_removed(self) -> None:
        assert not hasattr(SynthesizedMacro, "to_yaml")

    def test_skill_to_yaml_still_present_and_works(self) -> None:
        assert hasattr(SynthesizedSkill, "to_yaml")
        skill = SynthesizedSkill(name="n", description="d")
        yaml_str = skill.to_yaml()
        assert "name: n" in yaml_str
        assert "description: d" in yaml_str

    def test_macro_model_fields_intact(self) -> None:
        macro = SynthesizedMacro(
            name="m",
            description="md",
            namespace="n",
            trigger_patterns=["a"],
            source_thread_id="t",
            source_session_id="s",
        )
        assert macro.name == "m"
        assert macro.trigger_patterns == ["a"]
