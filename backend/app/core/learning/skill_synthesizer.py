"""
WorkflowSynthesizer - Phase 2 of Imitation Learning

This module synthesizes learned skills from trace sequences using LLM analysis.
It produces structured skill configurations that can be registered and executed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field

from app.constants import DEFAULT_PROJECT_ID

if TYPE_CHECKING:
    from app.core.execution.macro.schemas import MacroScript
from app.core.execution.macro.schemas import VerificationResponse
from app.core.learning.prompts import prompt_builder
from app.core.learning.schemas import SkillParameter
from app.core.learning.synthesizer_utils import cleanup_macro_steps
from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.i18n.service import i18n
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)

ALLOWED_UI_ACTIONS = {
    # Browser / DOM
    "goto",
    "navigate",
    "click",
    "type_text",
    "input",
    "key_press",
    "scroll",
    "wait",
    "wait_for",
    "extract",
    "get_text",
    "get_html",
    "get_attribute",
    "run_js",
    "evaluate",
    # Mobile / Android
    "tap",
    "long_press",
    "swipe",
    "input_text",
    "open_app",
    "back",
    "home",
    # Desktop / Global
    "applescript",
    "drag_drop",  # Automation Primitives
    "detect_pagination",
    "scroll_to_bottom",
    # System
    "screenshot",
    "dump",
    "dump_ui",
}

# Trace action names that pass ALLOWED_UI_ACTIONS but are not MacroActionType
# members — remap before constructing MacroStep (enum-validated).
_EVENT_TYPE_REMAP = {
    "goto": "navigate",
    "input_text": "input",
    "evaluate": "run_js",
    "dump": "dump_ui",
}


class SynthesisResult(BaseModel):
    """Output of a synthesis run: skill metadata plus an optional executable macro."""

    skill: SynthesizedSkill
    macro_script: Any = None


class SynthesizedSkill(DynamicBaseModel):
    """
    A complete learned skill configuration.
    This is the output of the synthesis process.
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


class WorkflowSynthesizer:
    """
    Synthesizer that uses TraceParser and produces SynthesizedSkill.
    """

    def __init__(self, thread_id: str, session_id: str | None = None):
        self.thread_id = thread_id
        self.session_id = session_id
        self.parser = TraceParser(thread_id, session_id)

    async def synthesize(self) -> SynthesisResult:
        """
        Main entry point: Parse trace -> Analyze with LLM -> Return SynthesisResult.
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
        yaml_output = await self._generate_skill_yaml(
            narrative, summary, sequence.initial_intent or ""
        )

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
            mode = verification.execution_mode
            mode_str = (
                str(mode.value)
                if hasattr(mode, "value")
                else str(mode)
                if mode
                else "deterministic"
            )
            logger.info(
                f"[{self.thread_id}] Using evolved macro: {len(macro_script_obj.steps)} -> {len(evolved_script.steps)} steps, "
                f"mode={mode_str}"
            )
        elif not verification.success:
            logger.warning(
                f"[{self.thread_id}] ⚠️ Verification failed: {verification.error_message or 'Unknown error'}. "
                f"Proceeding with unverified macro."
            )

        # Step 4.5: Parse YAML to SynthesizedSkill
        skill = self._parse_skill_yaml(yaml_output, sequence)

        # Prefer the evolved/compiled macro over LLM's version for reliability
        # (macro_script is returned separately, not stored on the skill DTO).
        logger.info(f"[{self.thread_id}] Finalizing skill with verified/compiled macro")

        return SynthesisResult(skill=skill, macro_script=macro_script_yaml)

    async def verify_macro(
        self, macro_script: str, project_id: int = DEFAULT_PROJECT_ID
    ) -> VerificationResponse:
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
        logger.info(
            f"[{self.thread_id}] Phase 5: Running agent-based macro verification"
        )

        from app.core.execution.macro.verification_service import SynthesisIntegration

        # verify_for_synthesis consumes a step list / MacroScript; a YAML string
        # would iterate char-by-char and always fail with "No valid steps".
        steps_input: object = macro_script
        if isinstance(macro_script, str):
            from app.utils.yaml import macro_from_yaml

            try:
                steps_input = macro_from_yaml(macro_script)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                logger.warning(
                    f"[{self.thread_id}] Failed to parse macro YAML for verification: {e}"
                )

        return await SynthesisIntegration.verify_for_synthesis(
            macro_script=steps_input, thread_id=self.thread_id, project_id=project_id
        )

    async def _generate_skill_yaml(
        self, narrative: str, summary: dict, user_intent_hint: str = ""
    ) -> str:
        """Use LLM to generate skill YAML from trace narrative."""
        from app.infrastructure.config.service import SystemConfigService

        user_lang = SystemConfigService.get_language_preference()
        language_constraint = i18n.get(
            "prompts.learning.synthesis_lang_constraint", lang=user_lang
        )

        prompt_vars = {
            "trace_narrative": narrative,
            "total_steps": summary["total_steps"],
            "human_steps": summary["human_steps"],
            "agent_steps": summary["agent_steps"],
            "tools_used": ", ".join(summary["tools_used"])
            if summary["tools_used"]
            else "None",
            "user_intent_hint": user_intent_hint,
            "language_constraint": language_constraint,
        }

        prompt = prompt_builder.build_synthesis_prompt(prompt_vars)

        logger.info(
            f"--- [Skill Synthesis Prompt Start] ---\n{prompt}\n--- [Skill Synthesis Prompt End] ---"
        )

        # Use InternalLLMService to prevent internal synthesis from being logged to chat
        from app.infrastructure.config.service import SystemConfigService
        from app.infrastructure.llm import InternalLLMService

        model_name = SystemConfigService.get_value("LLM_MODEL", "gpt-4o")
        response = await InternalLLMService.invoke(
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": prompt_builder.build_synthesis_human_prompt(),
                },
            ],
            purpose="skill_synthesis",
            model_name=model_name,
        )
        content = response.content

        logger.info(
            f"--- [Skill Synthesis Response Start] ---\n{content}\n--- [Skill Synthesis Response End] ---"
        )

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
            if step.action_type in (
                "node_start",
                "llm_output",
                "tool_result",
                "macro_thought",
            ):
                continue

            # Determine source
            source_type = MacroSource.DOM
            current_package = step.state_context.get("app_name") or step.node_name

            if step.action_name == "mobile_control":
                source_type = MacroSource.MOBILE
            elif step.action_name == "desktop_control":
                source_type = MacroSource.DESKTOP
            elif step.state_context.get("source") == "mobile":
                # Android mirror recordings (tap/swipe/key_press normalized
                # by TraceParser) execute through the mobile controller.
                source_type = MacroSource.MOBILE
            elif step.node_name in ("global_observation", "mobile_interaction"):
                source_type = (
                    MacroSource.MOBILE
                    if step.state_context.get("is_mirrored")
                    else MacroSource.DESKTOP
                )

            # Detect App Transition (mobile only: the desktop controller has no
            # package-based launch, and MacroActionType has no LAUNCH_APP member)
            if source_type == MacroSource.MOBILE and current_package not in (
                "global_observation",
                "mobile_interaction",
                "unknown",
            ):
                if last_package and current_package != last_package:
                    system_apps = (
                        "com.android.launcher",
                        "com.android.systemui",
                        "android",
                        "scrcpy",
                    )
                    if not any(current_package.startswith(sys) for sys in system_apps):
                        logger.info(
                            f"[Synthesizer] App transition detected: {last_package} -> {current_package}"
                        )
                        steps.append(
                            MacroStep(
                                type=MacroStepType.ACTION,
                                event_type=MacroActionType.OPEN_APP,
                                source=source_type,
                                payload={"package_name": current_package},
                            )
                        )
                        # Stability wait
                        steps.append(
                            MacroStep(
                                type=MacroStepType.ACTION,
                                event_type=MacroActionType.WAIT,
                                source=source_type,
                                payload={"duration_ms": 1500},
                            )
                        )

                if not any(
                    current_package.startswith(sys)
                    for sys in (
                        "com.android.launcher",
                        "com.android.systemui",
                        "android",
                    )
                ):
                    last_package = current_package

            # Filter noisy keys
            if step.action_type == "key_press" and step.action_args.get("key") in (
                "Alt",
                "Shift",
                "Control",
                "Command",
                "Meta",
            ):
                continue

            event_type = step.action_type
            payload = dict(step.action_args)

            if current_package and current_package not in (
                "global_observation",
                "mobile_interaction",
                "unknown",
            ):
                payload["package_name"] = current_package

            # Tool Call Normalization
            if event_type == "tool_call":
                action_name = payload.get("action")
                if action_name:
                    event_type = action_name
                    if event_type == "navigate":
                        event_type = "goto"
                    elif event_type == "type_text":
                        event_type = "input"
                else:
                    tool_invoked = step.action_name
                    if tool_invoked == "wait_for":
                        event_type = "wait"
                        payload["duration_ms"] = float(payload.get("seconds", 1)) * 1000
                    else:
                        continue

            if event_type not in ALLOWED_UI_ACTIONS:
                continue

            # MacroStep.event_type is a MacroActionType enum; a few legacy trace
            # names are valid trace actions but not enum members.
            event_type = _EVENT_TYPE_REMAP.get(event_type, event_type)

            target_selector = (
                step.ui_context.element_selector if step.ui_context else None
            )

            # Map to MacroStep
            if event_type in ("get_text", "get_html", "get_attribute") or (
                step.action_name == "mobile_control"
                and payload.get("action") == "dump_ui"
            ):
                has_extract = True
                macro_step = MacroStep(
                    type=MacroStepType.EXTRACT,
                    extract_type=payload.get("action") or event_type,
                    key=f"data_{step.step_number}",
                    source=source_type,
                    target_selector=payload.get("selector") or target_selector,
                    payload=payload,
                )
            else:
                macro_step = MacroStep(
                    type=MacroStepType.ACTION,
                    event_type=event_type,
                    source=source_type,
                    target_selector=target_selector,
                    payload=payload,
                )

            steps.append(macro_step)

        if has_extract:
            steps.append(MacroStep(type=MacroStepType.DUMP))

        # Final cleanup and indexing
        clean_steps = self._cleanup_macro(
            [s.model_dump(exclude_none=True) for s in steps]
        )[0]
        return MacroScript(steps=clean_steps)

    @classmethod
    def _cleanup_macro(
        cls, steps: list[dict], start_index: int = 1
    ) -> tuple[list[dict], int]:
        """规范化 LLM 生成的宏步骤 (修复常见格式错误并确保全局步骤编号唯一)"""
        return cleanup_macro_steps(steps, start_index)

    def _parse_skill_yaml(
        self, yaml_str: str, sequence: TraceSequence
    ) -> SynthesizedSkill:
        """Parse YAML string into SynthesizedSkill object."""
        try:
            data = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse skill YAML: {e}")
            raise ValueError(f"Failed to parse generated skill YAML: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("Generated skill YAML is not a mapping")

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

        # LLM may emit macro_script, but the compiled macro from the trace is
        # authoritative and returned separately in SynthesisResult. Ignore the
        # LLM-generated macro here to keep skill metadata separate from the
        # executable script.

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
