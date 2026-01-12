"""
Enhanced WorkflowSynthesizer - Phase 2 of Imitation Learning

This module synthesizes learned skills from trace sequences using LLM analysis.
It produces structured skill configurations that can be registered and executed.

Key Enhancements over Original:
- Uses TraceParser for structured input
- Supports human action traces
- Generates parameterized skills with trigger patterns
- Produces LearnedSkill configurations (not just Agent YAML)
"""

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.core.llm.factory import LLMFactory

logger = logging.getLogger("evoloop.learning.synthesizer")


@dataclass
class SkillParameter:
    """A parameter for a learned skill."""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: str | None = None


@dataclass
class SkillStep:
    """A single step in a skill execution plan."""
    action: str  # Tool name or action type
    args: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None  # Optional condition for this step
    on_error: str | None = None  # Error handling strategy


@dataclass
class LearnedSkill:
    """
    A complete learned skill configuration.
    This is the output of the synthesis process.
    """
    name: str
    description: str
    trigger_patterns: list[str] = field(default_factory=list)
    parameters: list[SkillParameter] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    steps: list[SkillStep] = field(default_factory=list)

    # Metadata
    source_thread_id: str | None = None
    source_session_id: str | None = None
    tools_used: list[str] = field(default_factory=list)

    def to_yaml(self) -> str:
        """Convert to YAML for storage/display."""
        return yaml.dump(asdict(self), default_flow_style=False, allow_unicode=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


SKILL_SYNTHESIS_PROMPT = """
You are the "Meta-Architect" for EvoLoop's Imitation Learning System.

## Your Task
Analyze the following task trace and synthesize a **reusable skill** that can automate this behavior.

## Input Trace
{trace_narrative}

## Trace Summary
- Total Steps: {total_steps}
- Human Steps: {human_steps}
- Agent Steps: {agent_steps}
- Tools Used: {tools_used}

## Output Requirements
Generate a skill configuration in YAML format with these fields:

```yaml
name: skill_name_snake_case
description: >
  Clear, concise description of what this skill does
trigger_patterns:
  - "Pattern 1: what user might say to trigger this"
  - "Pattern 2: alternative phrasing"
parameters:
  - name: param1
    type: string|number|boolean|path
    description: What this parameter represents
    required: true|false
preconditions:
  - "Any requirement before skill can run"
steps:
  - action: tool_name
    args:
      arg1: "{{param1}}"  # Use {{param}} for parametrization
  - action: another_tool
    args:
      target: "{{derived_value}}"
    condition: "if previous step succeeded"
```

## Rules
1. **Generalize**: Replace specific values with parameters (e.g., "auth.py" → {{filename}})
2. **Minimal Steps**: Only include necessary steps, skip redundant ones
3. **Human Actions**: Convert UI interactions to equivalent tool calls if possible
4. **Trigger Patterns**: Create 2-3 natural language patterns that would trigger this skill
5. **Valid YAML**: Output ONLY valid YAML, no explanations
"""


class EnhancedWorkflowSynthesizer:
    """
    Enhanced synthesizer that uses TraceParser and produces LearnedSkill.
    """

    def __init__(self, thread_id: str, session_id: str | None = None):
        self.thread_id = thread_id
        self.session_id = session_id
        self.parser = TraceParser(thread_id, session_id)

    async def synthesize(self) -> LearnedSkill:
        """
        Main entry point: Parse trace -> Analyze with LLM -> Return LearnedSkill.
        """
        # Step 1: Parse trace into structured sequence
        sequence = await self.parser.parse()

        if not sequence.steps:
            raise ValueError(f"No trace data found for thread {self.thread_id}")

        # Step 2: Convert to narrative for LLM
        narrative = self.parser.to_narrative(sequence)
        summary = sequence.summarize()

        # Step 3: Call LLM to synthesize skill
        yaml_output = await self._generate_skill_yaml(narrative, summary)

        # Step 4: Parse YAML to LearnedSkill
        skill = self._parse_skill_yaml(yaml_output, sequence)

        return skill

    async def _generate_skill_yaml(self, narrative: str, summary: dict) -> str:
        """Use LLM to generate skill YAML from trace narrative."""
        # Config is handled internally by LLMFactory
        llm = LLMFactory.create_llm()

        prompt = SKILL_SYNTHESIS_PROMPT.format(
            trace_narrative=narrative,
            total_steps=summary["total_steps"],
            human_steps=summary["human_steps"],
            agent_steps=summary["agent_steps"],
            tools_used=", ".join(summary["tools_used"]) if summary["tools_used"] else "None"
        )

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Please analyze the trace and generate the skill YAML.")
        ]

        response = await llm.ainvoke(messages, config={"callbacks": []})  # Internal thought, do not stream
        content = response.content

        # Strip markdown fences
        if "```yaml" in content:
            content = content.split("```yaml")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content

    def _parse_skill_yaml(self, yaml_str: str, sequence: TraceSequence) -> LearnedSkill:
        """Parse YAML string into LearnedSkill object."""
        try:
            data = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse skill YAML: {e}")
            # Return a minimal skill on parse failure
            return LearnedSkill(
                name="unparsed_skill",
                description="Failed to parse generated skill",
                source_thread_id=self.thread_id,
                source_session_id=self.session_id
            )

        # Extract parameters
        parameters = []
        for p in data.get("parameters", []):
            if isinstance(p, dict):
                parameters.append(SkillParameter(
                    name=p.get("name", "unknown"),
                    type=p.get("type", "string"),
                    description=p.get("description", ""),
                    required=p.get("required", True)
                ))

        # Extract steps
        steps = []
        for s in data.get("steps", []):
            if isinstance(s, dict):
                steps.append(SkillStep(
                    action=s.get("action", "unknown"),
                    args=s.get("args", {}),
                    condition=s.get("condition"),
                    on_error=s.get("on_error")
                ))

        return LearnedSkill(
            name=data.get("name", "unnamed_skill"),
            description=data.get("description", ""),
            trigger_patterns=data.get("trigger_patterns", []),
            parameters=parameters,
            preconditions=data.get("preconditions", []),
            steps=steps,
            source_thread_id=self.thread_id,
            source_session_id=self.session_id,
            tools_used=list(set(sequence.tools_used))
        )


# Backward compatibility alias
WorkflowSynthesizer = EnhancedWorkflowSynthesizer
