"""
WorkflowSynthesizer - Phase 2 of Imitation Learning

This module synthesizes learned skills from trace sequences using LLM analysis.
It produces structured skill configurations that can be registered and executed.
"""

import logging
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.core.llm.factory import LLMFactory
from app.infrastructure.database.sql.database import session_scope
from app.models import Message, LearnedSkill
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
    instructions: str | None = None  # Markdown instructions (心法)

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
Analyze the following task trace and synthesize a **reusable skill** that can automate this specific workflow.

## Input Trace
{trace_narrative}

## Trace Summary
- Total Steps: {total_steps} | Human Steps: {human_steps} | Agent Steps: {agent_steps}
- Tools Used: {tools_used}

## Output Requirements
Generate a skill configuration in YAML format.

**CRITICAL: The `instructions` field must be a structured "Expert Guide" (SOP) with the following sections:**

### 1. Conceptual Mental Model
Explain the **high-level strategy** and business logic. Why are we doing this? What's the goal?

### 2. Contextual Anchors
Define the expected environment:
- **App/OS Context**: e.g., "Obsidian must be open in a valid vault."
- **Visual Evidence**: What specific window titles or UI labels confirm we are in the right state?

### 3. Step-by-Step Strategic Guidance
For each major phase, provide "Rule of Thumb" advice:
- **Visual Cues**: "Look for the [Label] icon near the [Position]."
- **Hidden Logic**: "Wait 1 second for the sync icon to disappear before clicking save."
- **Common Pitfalls**: "Do not use the Cmd+N shortcut here as it sometimes fails in this app version; use the UI button instead."

### 4. Error Recovery SOP
If a visual anchor is missing, what's the fallback? (e.g., "Refresh the page" or "Check if the side panel is collapsed").

```yaml
name: create_obsidian_note
description: >
  Create a new note in Obsidian and tag it with a category. 
  Involves: [Obsidian]
trigger_patterns:
  - "Create a note named {{title}} in Obsidian"
parameters:
  - name: title
    type: string
    description: Title of the note
preconditions:
  - "Obsidian app is open"
steps:
  - action: desktop_control
    trace_step_ref: 2
    args:
      action: "click"
      element_text: "New Note"
    visual_context:
      element_text: "New Note"
instructions: |
  # Expert SOP: Creating Categorized Notes
  
  ## 1. Mental Model
  This skill focuses on prompt note creation while bypassing complex navigation.
  
  ## 2. Contextual Anchors
  - **Environment**: Obsidian Desktop (macOS/Windows).
  - **Visual Evidence**: Look for the 'Purple Obsidian Logo' in the title bar.
  
  ## 3. Strategic Guidance
  - **Phase 1 (Creation)**: Use the 'New Note' button. **Visual Cue**: It's the leftmost icon in the top toolbar.
  - **Phase 2 (Naming)**: The focus shifts to the title field automatically. **Pitfall**: Don't click the title bar again, it may cause a rename conflict.
  
  ## 4. Recovery
  - If 'New Note' button is hidden, check if the Left Sidebar is collapsed (Look for the '>' icon).
```

## Anti-Hallucination & Platform Rules
1. **STAY GROUNDED**: Do NOT invent "generic numeric keyboards" if they are not in the trace. 
2. **CONTEXT IS KING**: The `description` MUST mention the specific applications found in the trace.
3. **OCR Usage**: If `UI Element` text is provided in a trace step, **YOU MUST USE IT** for the `element_text` argument.
"""


class WorkflowSynthesizer:
    """
    Synthesizer that uses TraceParser and produces LearnedSkill.
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

        # [NEW] Step 1.5: Trigger Alignment - Fetch first user message
        first_user_msg = ""
        try:
            async with session_scope() as db:
                stmt = select(Message).where(
                    Message.thread_id == self.thread_id,
                    Message.role == "human"
                ).order_by(Message.created_at).limit(1)
                res = await db.execute(stmt)
                msg = res.scalar_one_or_none()
                if msg:
                    first_user_msg = msg.content
        except Exception as e:
            logger.warning(f"[Synthesizer] Failed to fetch first human msg: {e}")

        # Step 2: Convert to narrative for LLM
        narrative = self.parser.to_narrative(sequence)
        summary = sequence.summarize()

        # Step 3: Call LLM to synthesize skill
        # Pass first_user_msg to help align triggers
        yaml_output = await self._generate_skill_yaml(narrative, summary, first_user_msg)

        # Step 4: Parse YAML to LearnedSkill
        skill = self._parse_skill_yaml(yaml_output, sequence)

        # [NEW] Step 4.5: Deduplication check
        try:
            from app.core.learning.discovery import skill_discovery
            # Search for similar skills using the synthesized name/description
            _, relevant = await skill_discovery.discover(skill.description or skill.name, top_k=1)
            if relevant:
                # Potential log or UI notification for deduplication in the future
                logger.info(f"[Synthesizer] Found potential duplicate skill: {relevant[0].name}")
        except Exception as e:
            logger.warning(f"[Synthesizer] Deduplication check failed: {e}")

        # Step 5: Post-synthesis optimization (Redundancy removal)
        if auto_optimize:
            skill.steps = self._optimize_steps(skill.steps)

        return skill

    async def _generate_skill_yaml(self, narrative: str, summary: dict, user_intent_hint: str = "") -> str:
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

        if user_intent_hint:
            prompt += f"\n\n## User Intent Hint (Use this for trigger_patterns):\n\"{user_intent_hint}\""

        from app.core.system import SystemConfigService

        user_lang = SystemConfigService.get_language_preference()
        prompt += i18n.get("prompts.learning.synthesis_lang_constraint", lang=user_lang)

        logger.info(f"--- [Skill Synthesis Prompt Start] ---\n{prompt}\n--- [Skill Synthesis Prompt End] ---")

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Please analyze the trace and generate the skill YAML."),
        ]

        response = await llm.ainvoke(messages, config={"callbacks": []})  # Internal thought, do not stream
        content = response.content

        logger.info(f"--- [Skill Synthesis Response Start] ---\n{content}\n--- [Skill Synthesis Response End] ---")

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
            instructions=data.get("instructions"),
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
