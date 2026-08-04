"""
WorkflowSynthesizer - Phase 2 of Imitation Learning

This module synthesizes workflow artifacts from trace sequences using LLM analysis.
It produces either:
  - a learned skill configuration (`SynthesizedSkill`), or
  - a macro metadata record (`SynthesizedMacro`).

The mode is selected at construction time; the prompt, parser, and output model
are decoupled between the two modes while the underlying trace analysis is shared.
"""

from __future__ import annotations

import logging
from enum import Enum

import yaml
from pydantic import BaseModel, Field

from app.core.learning.prompts import prompt_builder
from app.core.learning.schemas import SkillParameter
from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.i18n.service import i18n
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class SynthesisMode(str, Enum):
    """Workflow synthesis mode."""

    SKILL = "skill"
    MACRO = "macro"


class SynthesizedSkill(DynamicBaseModel):
    """
    A complete learned skill configuration.
    This is the output of skill synthesis.
    """

    name: str
    description: str
    namespace: str = "misc"  # Logical grouping (e.g. os/macos, web/research)
    trigger_patterns: list[str] = Field(default_factory=list)
    parameters: list[SkillParameter] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    instructions: str | None = None  # Markdown instructions (心法)

    # Metadata
    source_thread_id: str | None = None
    source_session_id: str | None = None
    tools_used: list[str] = Field(default_factory=list)

    def to_yaml(self) -> str:
        """Convert to YAML for storage/display."""
        return yaml.dump(
            self.model_dump(),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


class SynthesizedMacro(DynamicBaseModel):
    """
    Metadata for a deterministic macro record.
    This is the output of macro metadata synthesis.
    """

    name: str
    description: str
    namespace: str = "misc"  # Logical grouping (e.g. os/macos, web/research)
    trigger_patterns: list[str] = Field(default_factory=list)
    parameters: list[SkillParameter] = Field(default_factory=list)

    # Metadata
    source_thread_id: str | None = None
    source_session_id: str | None = None

    def to_yaml(self) -> str:
        """Convert to YAML for storage/display."""
        return yaml.dump(
            self.model_dump(),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


class SynthesisResult(BaseModel):
    """Output of a synthesis run: contains either a skill or a macro artifact."""

    skill: SynthesizedSkill | None = None
    macro: SynthesizedMacro | None = None


class WorkflowSynthesizer:
    """
    Synthesizer that uses TraceParser and produces either a SynthesizedSkill
    or a SynthesizedMacro, depending on the configured mode.
    """

    def __init__(
        self,
        thread_id: str,
        session_id: str | None = None,
        sequence: TraceSequence | None = None,
        macro_script: str | None = None,
        mode: SynthesisMode | str = SynthesisMode.SKILL,
    ):
        self.thread_id = thread_id
        self.session_id = session_id
        self.parser = TraceParser(thread_id, session_id)
        self.sequence = sequence
        self.macro_script = macro_script
        if not isinstance(mode, SynthesisMode):
            mode = SynthesisMode(mode)
        self.mode = mode

    async def synthesize(self) -> SynthesisResult:
        """
        Main entry point: Parse trace (if needed) -> Analyze with LLM -> Return SynthesisResult.
        """
        # Step 1: Parse trace into structured sequence (or reuse injected sequence)
        sequence = self.sequence
        if sequence is None:
            sequence = await self.parser.parse()

        if not sequence.steps:
            raise ValueError(f"No trace data found for thread {self.thread_id}")

        # Step 2: Convert to narrative for LLM
        narrative = self.parser.to_narrative(sequence)

        # Step 3: Call LLM to synthesize the appropriate artifact
        yaml_output = await self._generate_yaml(
            narrative,
            sequence.summarize().model_dump(),
            sequence.initial_intent or "",
            self.macro_script or "",
        )

        # Step 4: Parse YAML into the appropriate artifact
        if self.mode == SynthesisMode.MACRO:
            artifact = self._parse_yaml_macro(yaml_output)
            logger.info(f"[{self.thread_id}] Finalizing macro synthesis")
            return SynthesisResult(macro=artifact)

        artifact = self._parse_yaml_skill(yaml_output, sequence)
        logger.info(f"[{self.thread_id}] Finalizing skill synthesis")
        return SynthesisResult(skill=artifact)

    async def _generate_yaml(
        self,
        narrative: str,
        summary: dict,
        user_intent_hint: str = "",
        macro_script: str = "",
    ) -> str:
        """Use LLM to generate YAML metadata from trace narrative and compiled macro script."""
        from app.infrastructure.config.service import SystemConfigService

        lang_code = SystemConfigService.get_value("LANGUAGE", "zh")
        language_constraint = i18n.get("learning.synthesis_lang_constraint", lang=lang_code)

        prompt_vars = {
            "trace_narrative": narrative,
            "macro_script": macro_script,
            "total_steps": summary["total_steps"],
            "human_steps": summary["human_steps"],
            "agent_steps": summary["agent_steps"],
            "tools_used": ", ".join(summary["tools_used"])
            if summary["tools_used"]
            else "None",
            "user_intent_hint": user_intent_hint,
            "language_constraint": language_constraint,
        }

        if self.mode == SynthesisMode.MACRO:
            prompt = prompt_builder.build_macro_metadata_synthesis_prompt(prompt_vars)
        else:
            prompt = prompt_builder.build_skill_synthesis_prompt(prompt_vars)

        logger.info(
            f"--- [{self.mode.value.title()} Synthesis Prompt Start] ---\n{prompt}\n--- [{self.mode.value.title()} Synthesis Prompt End] ---"
        )

        # Use InternalLLMService to prevent internal synthesis from being logged to chat
        from app.infrastructure.llm import InternalLLMService

        response = await InternalLLMService.invoke(
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": prompt_builder.build_synthesis_human_prompt(),
                },
            ],
            purpose="skill_synthesis",
            max_tokens=4000,
        )
        content = response.content

        logger.info(f"--- [{self.mode.value.title()} Synthesis Response Start] ---\n{content}\n--- [{self.mode.value.title()} Synthesis Response End] ---")

        # Strip markdown fences
        if "```yaml" in content:
            content = content.split("```yaml")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content

    def _load_yaml_data(self, yaml_str: str) -> dict:
        """Parse YAML string into a dict; raise ValueError on failure."""
        try:
            data = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse synthesis YAML: {e}")
            raise ValueError(f"Failed to parse generated synthesis YAML: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("Generated synthesis YAML is not a mapping")
        return data

    def _extract_parameters(self, data: dict) -> list[SkillParameter]:
        """Extract parameters from parsed YAML data."""
        parameters = []
        for p in data.get("parameters", []):
            if isinstance(p, dict):
                parameters.append(
                    SkillParameter(
                        name=p.get("name", "unknown"),
                        type=p.get("type", "string"),
                        description=p.get("description", ""),
                        required=p.get("required", True),
                    )
                )
        return parameters

    def _parse_yaml_macro(self, yaml_str: str) -> SynthesizedMacro:
        """Parse YAML string into a SynthesizedMacro."""
        data = self._load_yaml_data(yaml_str)
        parameters = self._extract_parameters(data)
        return SynthesizedMacro(
            name=data.get("name", "unnamed_macro"),
            description=data.get("description", ""),
            namespace=data.get("namespace", "misc"),
            trigger_patterns=data.get("trigger_patterns", []),
            parameters=parameters,
            source_thread_id=self.thread_id,
            source_session_id=self.session_id,
        )

    def _parse_yaml_skill(self, yaml_str: str, sequence: TraceSequence) -> SynthesizedSkill:
        """Parse YAML string into a SynthesizedSkill."""
        data = self._load_yaml_data(yaml_str)
        parameters = self._extract_parameters(data)

        # LLM may emit macro_script, but the compiled macro from the trace is
        # authoritative and returned separately. Ignore the LLM-generated macro
        # here to keep skill metadata separate from the executable script.

        return SynthesizedSkill(
            name=data.get("name", "unnamed_skill"),
            description=data.get("description", ""),
            namespace=data.get("namespace", "misc"),
            trigger_patterns=data.get("trigger_patterns", []),
            parameters=parameters,
            preconditions=data.get("preconditions", []),
            instructions=data.get("instructions"),
            source_thread_id=self.thread_id,
            source_session_id=self.session_id,
            tools_used=list(set(sequence.tools_used)),
        )

    def _parse_yaml(self, yaml_str: str, sequence: TraceSequence | None) -> SynthesizedSkill | SynthesizedMacro:
        """Backward-compatible dispatcher; kept for existing unit tests."""
        if self.mode == SynthesisMode.MACRO:
            return self._parse_yaml_macro(yaml_str)
        seq = sequence or TraceSequence(thread_id=self.thread_id)
        return self._parse_yaml_skill(yaml_str, seq)
