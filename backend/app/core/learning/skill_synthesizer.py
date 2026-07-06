"""
WorkflowSynthesizer - Phase 2 of Imitation Learning

This module synthesizes learned skills from trace sequences using LLM analysis.
It produces structured skill configurations that can be registered and executed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import yaml
from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings

if TYPE_CHECKING:
    from app.core.execution.macro.schemas import MacroScript
from app.core.execution.macro.schemas import VerificationResponse
from app.core.learning.prompts import prompt_builder
from app.core.learning.schemas import SkillParameter
from app.core.learning.synthesizer_utils import (
    cleanup_macro_steps,
    export_skill_to_filesystem,
)
from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.i18n.service import i18n
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)

ALLOWED_UI_ACTIONS = {
    # Browser / DOM
    "goto", "navigate", "click", "type_text", "input", "key_press", "scroll",
    "wait", "wait_for", "extract", "get_text", "get_html", "get_attribute",
    "run_js", "evaluate",
    # Mobile / Android
    "tap", "long_press", "swipe", "input_text", "open_app", "back", "home",
    # Desktop / Global
    "applescript", "drag_drop", # Automation Primitives
    "detect_pagination", "scroll_to_bottom",
    # System
    "screenshot", "dump", "dump_ui"
}


class SynthesizedSkill(DynamicBaseModel):
    """
    A complete learned skill configuration.
    This is the output of the synthesis process.
    """
    name: str
    description: str
    namespace: str = "misc"  # Logical grouping (e.g., os/macos, web/research)
    trigger_patterns: list[str] = Field(default_factory=list)
    parameters: list[SkillParameter] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    instructions: str | None = None  # Markdown instructions (心法)

    # Deterministic Execution
    execution_mode: str = "agentic" # "agentic" or "deterministic"
    macro_script: str = ""  # YAML format for storage and execution

    # Metadata
    source_thread_id: str | None = None
    source_session_id: str | None = None
    tools_used: list[str] = Field(default_factory=list)

    def to_yaml(self) -> str:
        """Convert to YAML for storage/display."""
        return yaml.dump(self.model_dump(), default_flow_style=False, allow_unicode=True, sort_keys=False)


class WorkflowSynthesizer:
    """
    Synthesizer that uses TraceParser and produces SynthesizedSkill.
    """

    def __init__(self, thread_id: str, session_id: str | None = None):
        self.thread_id = thread_id
        self.session_id = session_id
        self.parser = TraceParser(thread_id, session_id)

    async def synthesize(self, auto_optimize: bool = True) -> SynthesizedSkill:
        """
        Main entry point: Parse trace -> Analyze with LLM -> Return SynthesizedSkill.
        """
        # Step 1: Parse trace into structured sequence
        sequence = await self.parser.parse()

        if not sequence.steps:
            raise ValueError(f"No trace data found for thread {self.thread_id}")

        # Step 2: Convert to narrative for LLM
        narrative = self.parser.to_narrative(sequence)
        summary = sequence.summarize()

        # Step 3: Call LLM to synthesize skill
        # Use initial_intent captured by the parser to align triggers
        yaml_output = await self._generate_skill_yaml(narrative, summary, sequence.initial_intent or "")

        # Step 4.2: Compile raw trace into structured MacroScript
        macro_script_obj = self._compile_macro_script(sequence)
        macro_script_yaml = macro_script_obj.to_yaml()

        # [Phase 5] Step 4.3: Agent-based Macro Verification
        # We verify and evolve the macro BEFORE calling the expensive LLM (if needed)
        verification = await self.verify_macro(macro_script_yaml)

        # Use evolved macro if available
        if verification.success and verification.evolved_macro:
            from app.core.execution.macro.schemas import MacroScript
            evolved_script = MacroScript(steps=verification.evolved_macro)
            macro_script_yaml = evolved_script.to_yaml()
            
            logger.info(
                f"[{self.thread_id}] Using evolved macro: {len(macro_script_obj.steps)} -> {len(evolved_script.steps)} steps, "
                f"mode={verification.execution_mode if verification.execution_mode else 'unknown'}"
            )
        elif not verification.success:
            logger.warning(
                f"[{self.thread_id}] ⚠️ Verification failed: {verification.error_message or 'Unknown error'}. "
                f"Proceeding with unverified macro."
            )

        # Step 4.5: Parse YAML to SynthesizedSkill and inject macro
        skill = self._parse_skill_yaml(yaml_output, sequence)

        # Prefer the evolved/compiled macro over LLM's version for reliability
        if not skill.macro_script or verification.success:
            skill.macro_script = macro_script_yaml
            logger.info(f"[{self.thread_id}] Finalizing skill with verified/compiled macro")

        # Set execution mode based on verification results
        if verification.success:
            # Ensure it's a string for DB/YAML consistency
            mode = verification.execution_mode
            if hasattr(mode, "value"):
                skill.execution_mode = str(mode.value)
            else:
                skill.execution_mode = str(mode) if mode else "deterministic"
            
            confidence = verification.confidence_score or 0
            logger.info(
                f"[{self.thread_id}] Verified execution mode for {skill.name}: "
                f"{skill.execution_mode} (confidence: {confidence:.2%})"
            )
        else:
            skill.execution_mode = "agentic"
            logger.warning(f"[{self.thread_id}] Using 'agentic' mode due to verification failure")

        # Step 5: Physical File Export (Phase 5)
        self._export_physical_skill(skill)

        return skill

    async def verify_macro(self, macro_script: str, project_id: int = DEFAULT_PROJECT_ID) -> VerificationResponse:
        """
        [Phase 5] Agent-based verification of a draft macro.

        Replaces the old dry-run verification with active agent-based verification
        that detects anomalies and evolves the macro for better robustness.

        Args:
            macro_script: The compiled macro from trace
            project_id: Project ID for environment context

        Returns:
            Verification result with evolved macro if improvements were made
        """
        logger.info(f"[{self.thread_id}] Phase 5: Running agent-based macro verification")

        from app.core.execution.macro.verification_service import SynthesisIntegration
        return await SynthesisIntegration.verify_for_synthesis(
            macro_script=macro_script,
            thread_id=self.thread_id,
            project_id=project_id
        )

    async def _generate_skill_yaml(self, narrative: str, summary: dict, user_intent_hint: str = "") -> str:
        """Use LLM to generate skill YAML from trace narrative."""
        from app.infrastructure.config.service import SystemConfigService
        user_lang = SystemConfigService.get_language_preference()
        language_constraint = i18n.get("prompts.learning.synthesis_lang_constraint", lang=user_lang)

        prompt_vars = {
            "trace_narrative": narrative,
            "total_steps": summary["total_steps"],
            "human_steps": summary["human_steps"],
            "agent_steps": summary["agent_steps"],
            "tools_used": ", ".join(summary["tools_used"]) if summary["tools_used"] else "None",
            "user_intent_hint": user_intent_hint,
            "language_constraint": language_constraint
        }

        prompt = prompt_builder.build_synthesis_prompt(prompt_vars)

        logger.info(f"--- [Skill Synthesis Prompt Start] ---\n{prompt}\n--- [Skill Synthesis Prompt End] ---")

        # Use InternalLLMService to prevent internal synthesis from being logged to chat
        from app.infrastructure.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL", "gpt-4o")
        response = await InternalLLMService.invoke(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": prompt_builder.build_synthesis_human_prompt()},
            ],
            purpose="skill_synthesis",
            model_name=model_name,
        )
        content = response.content

        logger.info(f"--- [Skill Synthesis Response Start] ---\n{content}\n--- [Skill Synthesis Response End] ---")

        # Strip markdown fences
        if "```yaml" in content:
            content = content.split("```yaml")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content

    def _compile_macro_script(self, sequence: TraceSequence) -> MacroScript:
        """Compile raw TraceSteps into a clean structured MacroScript."""
        from app.core.execution.macro.schemas import (
            MacroActionType,
            MacroScript,
            MacroSource,
            MacroStep,
            MacroStepType,
        )
        
        steps = []
        has_extract = False
        last_package = None

        for step in sequence.steps:
            # Skip non-UI/agentic control events
            if step.action_type in ("node_start", "llm_output", "tool_result", "macro_thought"):
                continue

            # Determine source
            source_type = MacroSource.DOM
            current_package = step.state_context.get("app_name") or step.node_name

            if step.action_name == "mobile_control":
                source_type = MacroSource.MOBILE
            elif step.action_name == "desktop_control":
                source_type = MacroSource.DESKTOP
            elif step.node_name in ("global_observation", "mobile_interaction"):
                source_type = MacroSource.MOBILE if step.state_context.get("is_mirrored") else MacroSource.DESKTOP

            # Detect App Transition
            if source_type in (MacroSource.MOBILE, MacroSource.DESKTOP) and current_package not in ("global_observation", "mobile_interaction", "unknown"):
                if last_package and current_package != last_package:
                    system_apps = (settings.SERVICE_NAME, "com.android.launcher", "com.android.systemui", "android", "scrcpy")
                    if not any(current_package.startswith(sys) for sys in system_apps):
                        logger.info(f"[Synthesizer] App transition detected: {last_package} -> {current_package}")
                        steps.append(MacroStep(
                            type=MacroStepType.ACTION,
                            event_type=MacroActionType.OPEN_APP if source_type == MacroSource.MOBILE else MacroActionType.LAUNCH_APP,
                            source=source_type,
                            payload={"package_name": current_package}
                        ))
                        # Stability wait
                        steps.append(MacroStep(
                            type=MacroStepType.ACTION,
                            event_type=MacroActionType.WAIT,
                            source=source_type,
                            payload={"duration_ms": 1500}
                        ))

                if not any(current_package.startswith(sys) for sys in ("com.android.launcher", "com.android.systemui", "android")):
                    last_package = current_package

            # Filter noisy keys
            if step.action_type == "key_press" and step.action_args.get("key") in ("Alt", "Shift", "Control", "Command", "Meta"):
                continue

            event_type = step.action_type
            payload = dict(step.action_args)

            if current_package and current_package not in ("global_observation", "mobile_interaction", "unknown"):
                payload["package_name"] = current_package

            # Tool Call Normalization
            if event_type == "tool_call":
                action_name = payload.get("action")
                if action_name:
                    event_type = action_name
                    if event_type == "navigate": event_type = "goto"
                    elif event_type == "type_text": event_type = "input"
                else:
                    tool_invoked = step.action_name
                    if tool_invoked == "wait_for":
                        event_type = "wait"
                        payload["duration_ms"] = float(payload.get("seconds", 1)) * 1000
                    else:
                        continue

            if event_type not in ALLOWED_UI_ACTIONS:
                continue

            target_selector = step.ui_context.element_selector if step.ui_context else None

            # Map to MacroStep
            if event_type in ("get_text", "get_html", "get_attribute") or (step.action_name == "mobile_control" and payload.get("action") == "dump_ui"):
                has_extract = True
                macro_step = MacroStep(
                    type=MacroStepType.EXTRACT,
                    extract_type=payload.get("action") or event_type,
                    key=f"data_{step.step_number}",
                    source=source_type,
                    target_selector=payload.get("selector") or target_selector,
                    payload=payload
                )
            else:
                macro_step = MacroStep(
                    type=MacroStepType.ACTION,
                    event_type=event_type,
                    source=source_type,
                    target_selector=target_selector,
                    payload=payload
                )

            steps.append(macro_step)

        if has_extract:
            steps.append(MacroStep(type=MacroStepType.DUMP))

        # Final cleanup and indexing
        clean_steps = self._cleanup_macro([s.model_dump(exclude_none=True) for s in steps])[0]
        return MacroScript(steps=clean_steps)

    @classmethod
    def _cleanup_macro(cls, steps: list[dict], start_index: int = 1) -> tuple[list[dict], int]:
        """规范化 LLM 生成的宏步骤 (修复常见格式错误并确保全局步骤编号唯一)"""
        return cleanup_macro_steps(steps, start_index)

    def _parse_skill_yaml(self, yaml_str: str, sequence: TraceSequence) -> SynthesizedSkill:
        """Parse YAML string into SynthesizedSkill object."""
        try:
            data = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse skill YAML: {e}")
            return SynthesizedSkill(
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

        # Handle macro script from LLM output if present
        macro_script = ""
        raw_macro = data.get("macro_script")
        if raw_macro:
            from app.core.execution.macro.schemas import MacroScript
            if isinstance(raw_macro, list):
                macro_script = MacroScript(steps=raw_macro).to_yaml()
            else:
                macro_script = str(raw_macro)

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
            macro_script=macro_script,
        )

    def _export_physical_skill(self, skill: SynthesizedSkill) -> None:
        """
        Phase 5: Export the synthesized instructions into a physical workspace
        folder structure based on its namespace.
        """
        path = export_skill_to_filesystem(skill)
        if path:
            skill.resource_path = path
