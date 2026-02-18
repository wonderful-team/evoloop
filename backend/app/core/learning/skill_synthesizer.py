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
from uuid import uuid4

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.core.llm.factory import LLMFactory
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


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
    visual_context: dict[str, Any] | None = None  # UI element info (text, snapshot, bounds)
    children: list["SkillStep"] = field(default_factory=list)  # Nested steps for loops/if
    step_id: str = field(default_factory=lambda: str(uuid4()))  # Unique ID for UI tracking


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
    trace_step_ref: 1  # Original step number from trace (crucial for visual context)
    args:
      arg1: "{{param1}}"  # Use {{param}} for parametrization
  - action: another_tool
    trace_step_ref: 2
    args:
      target: "{{derived_value}}"
    condition: "if previous step succeeded"
```

## Platform Control Translation Rules
When synthesizing skills that involve Android or Mac interaction, use these mappings:

**Android (via `mobile_control`):**
- Tap at coordinates → `mobile_control(action="tap", x={{x}}, y={{y}})`
- Swipe gesture → `mobile_control(action="swipe", x={{start_x}}, y={{start_y}}, x2={{end_x}}, y2={{end_y}})`
- Type text → `mobile_control(action="input_text", text="{{text}}")`
- Press key → `mobile_control(action="press_key", keycode="{{key}}")`
- Take screenshot → `mobile_control(action="screenshot")`

**MacOS (via `desktop_control`):**
- Click at coordinates → `desktop_control(action="click", x={{x}}, y={{y}})`
- Type text → `desktop_control(action="type_text", text="{{text}}")`
- Open application → `desktop_control(action="open_app", app_name="{{app_name}}")`
- Press key → `desktop_control(action="key_press", key="{{key}}")`

**Best Practice**: If the trace contains UI element text (e.g., "clicked on '短信' button"), prefer using semantic element identification over fixed coordinates for better portability across devices.
**Requirement**: For every step that corresponds to a UI interaction (click, input), MUST include `trace_step_ref` field pointing to the original trace step number. This allows the system to attach screenshots and UI element data to the compiled skill.

## Rules
1. **Generalize**: Replace specific values with parameters (e.g., "auth.py" → {{filename}})
2. **Minimal Steps**: Only include necessary steps, skip redundant ones
3. **Human Actions**: Convert UI interactions to equivalent tool calls if possible
4. **Trigger Patterns**: Create 2-3 natural language patterns that would trigger this skill
5. **Valid YAML**: Output ONLY valid YAML, no explanations
6. **Trace References**: Include `trace_step_ref` for every step derived from the trace.
7. **Self-Correction Support**: For steps that are prone to failure (e.g., clicking a button that might not have loaded), add `on_error: "retry"` or `on_error: "ignore"`.
8. **Dynamic Parameters**: Always favor parameters for text inputs, file paths, and target search terms.
"""


class EnhancedWorkflowSynthesizer:
    """
    Enhanced synthesizer that uses TraceParser and produces LearnedSkill.
    """

    def __init__(self, thread_id: str, session_id: str | None = None):
        self.thread_id = thread_id
        self.session_id = session_id
        self.parser = TraceParser(thread_id, session_id)

    async def synthesize(self, auto_optimize: bool = True) -> LearnedSkill:
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

        # Step 5: Post-synthesis optimization (Redundancy removal)
        if auto_optimize:
            skill.steps = self._optimize_steps(skill.steps)

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
            tools_used=", ".join(summary["tools_used"]) if summary["tools_used"] else "None",
        )

        from app.core.system import SystemConfigService

        user_lang = SystemConfigService.get_language_preference()
        prompt += i18n.get("prompts.learning.synthesis_lang_constraint", lang=user_lang)

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Please analyze the trace and generate the skill YAML."),
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
            return LearnedSkill(
                name="unparsed_skill",
                description="Failed to parse generated skill",
                source_thread_id=self.thread_id,
                source_session_id=self.session_id,
            )

        # Extract parameters
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

        # Create a map for quick lookup of trace steps by step_number
        trace_steps_map = {step.step_number: step for step in sequence.steps}

        # Recursive helper for parsing steps
        def parse_step_node(s_dict: dict, trace_map: dict) -> SkillStep:
            step = SkillStep(
                action=s_dict.get("action", "unknown"),
                args=s_dict.get("args", {}),
                condition=s_dict.get("condition"),
                on_error=s_dict.get("on_error"),
            )

            # Sub-steps nesting
            if "children" in s_dict and isinstance(s_dict["children"], list):
                step.children = [parse_step_node(c, trace_map) for c in s_dict["children"]]

            # For Legacy "if" schemas in YAML (then/else logic)
            if "then" in s_dict:
                step.args["then"] = [parse_step_node(c, trace_map) for c in s_dict["then"]]
            if "else" in s_dict:
                step.args["else"] = [parse_step_node(c, trace_map) for c in s_dict["else"]]

            # Enrich with visual context
            ref_id = s_dict.get("trace_step_ref")
            if ref_id is not None:
                try:
                    ref_idx = int(ref_id)
                    if ref_idx in trace_map:
                        trace_step = trace_map[ref_idx]
                        if trace_step.ui_context:
                            step.visual_context = asdict(trace_step.ui_context)
                except (ValueError, TypeError):
                    pass
            return step

        # Extract steps
        steps = [
            parse_step_node(s, trace_steps_map)
            for s in data.get("steps", [])
            if isinstance(s, dict)
        ]

        return LearnedSkill(
            name=data.get("name", "unnamed_skill"),
            description=data.get("description", ""),
            trigger_patterns=data.get("trigger_patterns", []),
            parameters=parameters,
            preconditions=data.get("preconditions", []),
            steps=steps,
            source_thread_id=self.thread_id,
            source_session_id=self.session_id,
            tools_used=list(set(sequence.tools_used)),
        )

    def _optimize_steps(self, steps: list[SkillStep]) -> list[SkillStep]:
        """
        Apply heuristic optimizations to the synthesized steps.
        - Removes redundant consecutive taps on the same element.
        - Prunes empty logic blocks.
        """
        if not steps:
            return []

        optimized = []
        last_step = None

        for step in steps:
            # Recursive optimization for children
            if step.children:
                step.children = self._optimize_steps(step.children)

            # Heuristic 1: Remove redundant consecutive identical mobile/desktop actions
            # e.g., tapping the same coordinates or same text twice in a row
            if last_step and step.action == last_step.action and step.action in ["mobile_control", "desktop_control"]:
                if step.args == last_step.args:
                    logger.info(f"Pruning redundant consecutive action: {step.action}")
                    continue

            # Heuristic 2: Remove empty groups/loops
            if step.action in ["group", "loop"] and not step.children:
                logger.info(f"Pruning empty {step.action} block")
                continue

            optimized.append(step)
            last_step = step

        return optimized


# Backward compatibility alias
WorkflowSynthesizer = EnhancedWorkflowSynthesizer
