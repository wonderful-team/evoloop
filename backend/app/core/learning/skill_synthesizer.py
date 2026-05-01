"""
WorkflowSynthesizer - Phase 2 of Imitation Learning

This module synthesizes learned skills from trace sequences using LLM analysis.
It produces structured skill configurations that can be registered and executed.
"""

from __future__ import annotations

import logging

import yaml
from pydantic import Field
from sqlalchemy import select

from app.core.config import settings
from app.core.execution.macro.models import VerificationResponse
from app.core.learning.prompts import prompt_builder
from app.core.learning.schemas import SkillParameter
from app.core.learning.synthesizer_utils import (
    cleanup_macro_steps,
    export_skill_to_filesystem,
)
from app.core.learning.trace_parser import TraceParser, TraceSequence
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import Message

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

        # Step 4.2: Compile raw trace into deterministic macro JSON
        macro_script = self._compile_macro_script(sequence)

        # [Phase 5] Step 4.3: Agent-based Macro Verification
        # We verify and evolve the macro BEFORE calling the expensive LLM
        verification = await self.verify_macro(macro_script)

        # Use evolved macro if available
        if verification.success and verification.evolved_macro:
            evolved_steps = verification.evolved_macro
            # Count lines/steps in original YAML for comparison
            original_steps = yaml.safe_load(macro_script) if macro_script else []
            original_count = len(original_steps)
            evolved_count = len(evolved_steps)
            # Convert evolved steps back to YAML string
            macro_script = yaml.dump(evolved_steps, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info(
                f"[{self.thread_id}] Using evolved macro: {original_count} -> {evolved_count} steps, "
                f"mode={verification.execution_mode.value if verification.execution_mode else 'unknown'}"
            )
        elif not verification.success:
            logger.warning(
                f"[{self.thread_id}] ⚠️ Verification failed: {verification.error_message or 'Unknown error'}. "
                f"Proceeding with unverified macro."
            )
            # Don't abort - let the LLM have a chance to fix it

        # Step 4.5: Parse YAML to SynthesizedSkill and inject macro
        skill = self._parse_skill_yaml(yaml_output, sequence)

        # Prefer the evolved/compiled macro over LLM's version for reliability
        if not skill.macro_script:
            skill.macro_script = macro_script
            logger.info(f"[{self.thread_id}] Using compiled/evolved macro (No LLM macro found)")
        elif verification.status == "success":
            # Use evolved macro which is more robust
            skill.macro_script = macro_script
            logger.info(f"[{self.thread_id}] Using evolved macro over LLM version for reliability")
        else:
            logger.info(f"[{self.thread_id}] Using LLM-synthesized smart macro script")

        # Set execution mode based on verification results
        if verification.success:
            # Use the verified execution mode
            skill.execution_mode = verification.execution_mode.value if verification.execution_mode else "deterministic"
            confidence = verification.confidence_score or 0
            logger.info(
                f"[{self.thread_id}] Verified execution mode for {skill.name}: "
                f"{skill.execution_mode} (confidence: {confidence:.2%})"
            )
        else:
            # Fall back to agentic mode if verification failed
            skill.execution_mode = "agentic"
            logger.warning(f"[{self.thread_id}] Using 'agentic' mode due to verification failure")

        # [NEW] Step 5: Physical File Export (Phase 5)
        self._export_physical_skill(skill)

        return skill

    async def verify_macro(self, macro_script: str, project_id: int = 1) -> VerificationResponse:
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
        from app.core.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
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

    def _compile_macro_script(self, sequence: TraceSequence) -> str:
        """Compile raw TraceSteps into a clean deterministic macro YAML format."""
        macro = []
        has_extract = False
        last_package = None

        for step in sequence.steps:
            # [Phase 13] Explicitly skip agentic bridge events early
            if step.action_type in ("node_start", "llm_output", "tool_result", "macro_thought"):
                continue

            # Identify if this was a global (OS/Android) or DOM action
            source_type = "dom"
            current_package = step.state_context.app_name or step.node_name

            if step.action_name == "mobile_control":
                source_type = "mobile"
            elif step.action_name == "desktop_control":
                source_type = "desktop"
            elif step.node_name in ("global_observation", "mobile_interaction"):
                if step.state_context.is_mirrored:
                    source_type = "mobile"
                else:
                    source_type = "desktop"

            # Detect App Transition (Cross-App Support)
            # Only for mobile/desktop where app switching is a distinct action
            if source_type in ("mobile", "desktop") and current_package not in ("global_observation", "mobile_interaction", "unknown"):
                if last_package and current_package != last_package:
                    # Generic prefix logic (e.g. android, com.android.launcher are ignored)
                    system_apps = (settings.SERVICE_NAME, "com.android.launcher", "com.android.systemui", "android", "scrcpy", "com.android.settings")

                    # IGNORE system noise during transitions
                    # Note: We keep "com.android.settings" in case the user actually wants to automate settings,
                    # but usually it's noise if it's just a quick toggle. For now we treat it as a target if it's a switch.

                    is_current_system = any(current_package.startswith(sys) for sys in system_apps)

                    if not is_current_system:
                        logger.info(f"[Synthesizer] App transition detected: {last_package} -> {current_package}")
                        macro.append({
                            "step_number": len(macro) + 1,
                            "type": "action",
                            "event_type": "open_app" if source_type == "mobile" else "launch_app",
                            "source": source_type,
                            "payload": {"package_name": current_package}
                        })
                        # IMPORTANT: Add a stability wait after app switch to allow cold start/animation
                        macro.append({
                            "step_number": len(macro) + 1,
                            "type": "action",
                            "event_type": "wait",
                            "source": source_type,
                            "payload": {"duration_ms": 1500}
                        })

                # Update last_package only if the current one is NOT a system app or launcher noise
                # This ensures that if we briefly go to Launcher and back to App A, it's not a transition.
                system_noise = ("com.android.launcher", "com.android.systemui", "android", "scrcpy")
                if not any(current_package.startswith(sys) for sys in system_noise):
                    last_package = current_package

            # Filter out noisy standalone modifier keys from macro
            if step.action_type == "key_press" and step.action_args.get("key") in ("Alt", "Shift", "Control", "Command", "Meta"):
                continue

            event_type = step.action_type
            payload = dict(step.action_args)

            # Ensure package_name is in payload for all steps
            if current_package and current_package not in ("global_observation", "mobile_interaction", "unknown"):
                payload["package_name"] = current_package

            # Agent LangChain tool inputs...
            if "raw" in payload and isinstance(payload["raw"], str):
                import ast
                try:
                    parsed = ast.literal_eval(payload["raw"])
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
                    pass

            action_name = payload.get("action")

            # Map generic tool_call from Agents back to explicit macro events
            if event_type == "tool_call":
                if action_name:
                    event_type = action_name  # e.g. "click", "wait_for", "type_text"
                    if event_type == "navigate":
                        event_type = "goto"
                    elif event_type == "type_text":
                        event_type = "input"
                else:
                    tool_invoked = step.action_name
                    if tool_invoked == "wait_for":
                        event_type = "wait"
                        payload["duration_ms"] = float(payload.get("seconds", 1)) * 1000
                    elif tool_invoked == "memorize_concepts":
                        continue
                    elif tool_invoked in ("request_human_input", "research", "manage_todo", "document_reader"):
                        continue
                    else:
                        continue

            if event_type not in ALLOWED_UI_ACTIONS:
                logger.debug(f"[{self.thread_id}] Skipping non-UI action during synthesis: {event_type}")
                continue

            target_selector = step.ui_context.element_selector if step.ui_context else None

            # Automatic Extractor Nodes mapping
            is_extract = False
            if event_type in ("get_text", "get_html", "get_attribute"):
                macro_step = {
                    "step_number": len(macro) + 1,
                    "type": "extract",
                    "extract_type": action_name,
                    "key": f"data_{step.step_number}",
                    "source": "dom",
                    "target_selector": payload.get("selector") or target_selector,
                    "payload": payload
                }
                is_extract = True
            elif event_type == "tool_call" and step.action_name == "mobile_control" and action_name == "dump_ui":
                macro_step = {
                    "step_number": len(macro) + 1,
                    "type": "extract",
                    "extract_type": "dump_ui",
                    "key": f"data_{step.step_number}",
                    "source": source_type,
                    "target_selector": target_selector,
                    "payload": payload
                }
                is_extract = True
            else:
                macro_step = {
                    "step_number": len(macro) + 1,
                    "type": "action",
                    "event_type": event_type,
                    "source": source_type,
                    "target_selector": target_selector,
                    "payload": payload
                }

            if is_extract:
                has_extract = True

            macro.append(macro_step)

        # Append Dump Data Sink if any extraction occurred
        if has_extract:
            macro.append({
                "step_number": len(macro) + 1,
                "type": "dump",
                "payload": {}
            })

        # Macro optimization is now handled via MacroService in the main synthesize flow
        steps = self._cleanup_macro(macro)[0]
        # Convert to YAML string for storage
        return yaml.dump(steps, default_flow_style=False, allow_unicode=True, sort_keys=False)

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
            macro_script=yaml.dump(data.get("macro_script", []), default_flow_style=False, allow_unicode=True, sort_keys=False) if data.get("macro_script") else "",
        )

    def _export_physical_skill(self, skill: SynthesizedSkill) -> None:
        """
        Phase 5: Export the synthesized instructions into a physical workspace
        folder structure based on its namespace.
        """
        path = export_skill_to_filesystem(skill)
        if path:
            skill.resource_path = path
